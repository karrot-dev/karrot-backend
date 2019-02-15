from enum import Enum

from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from karrot.applications.stats import application_status_update
from karrot.applications.tasks import notify_about_accepted_application, notify_about_declined_application
from karrot.base.base_models import BaseModel
from karrot.conversations.models import ConversationMixin
from karrot.history.models import History, HistoryTypus
from karrot.utils import markdown


class ApplicationStatus(Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    WITHDRAWN = 'withdrawn'


class Application(BaseModel, ConversationMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    decided_at = models.DateTimeField(null=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='application_decided',
    )
    questions = models.TextField()
    answers = models.TextField()
    status = models.CharField(
        default=ApplicationStatus.PENDING.value,
        choices=[(status.value, status.value) for status in ApplicationStatus],
        max_length=100,
    )

    @property
    def has_ended(self):
        return self.status != ApplicationStatus.PENDING.value

    def questions_rendered(self, **kwargs):
        return markdown.render(self.questions, **kwargs)

    def answers_rendered(self, **kwargs):
        return markdown.render(self.answers, **kwargs)

    def save(self, **kwargs):
        old = type(self).objects.get(pk=self.pk) if self.pk else None
        super().save(**kwargs)
        if old is None or old.status != self.status:
            application_status_update(self)

    @transaction.atomic
    def accept(self, accepted_by):
        self.status = ApplicationStatus.ACCEPTED.value
        self.decided_by = accepted_by
        self.decided_at = timezone.now()
        self.save()
        self.group.add_member(
            self.user,
            added_by=accepted_by,
            history_payload={
                'accepted_by': accepted_by.id,
                'application_date': self.created_at.isoformat(),
            }
        )
        notify_about_accepted_application(self)

    @transaction.atomic
    def decline(self, declined_by):
        self.status = ApplicationStatus.DECLINED.value
        self.decided_by = declined_by
        self.decided_at = timezone.now()
        self.save()
        History.objects.create(
            typus=HistoryTypus.APPLICATION_DECLINED,
            group=self.group,
            users=[declined_by],
            payload={
                'applicant': self.user.id,
                'applicant_name': self.user.display_name,
                'application_date': self.created_at.isoformat()
            }
        )

        notify_about_declined_application(self)

    @transaction.atomic
    def withdraw(self):
        self.status = ApplicationStatus.WITHDRAWN.value
        self.decided_by = self.user
        self.decided_at = timezone.now()
        self.save()
