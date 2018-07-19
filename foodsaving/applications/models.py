from enum import Enum

from django.conf import settings
from django.db import models, transaction

from foodsaving.applications.tasks import notify_about_accepted_application, notify_about_declined_application
from foodsaving.base.base_models import BaseModel
from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils import markdown


class GroupApplicationStatus(Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    WITHDRAWN = 'withdrawn'


class GroupApplication(BaseModel):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    questions = models.TextField()
    answers = models.TextField()
    status = models.CharField(
        default=GroupApplicationStatus.PENDING.value,
        choices=[(status.value, status.value) for status in GroupApplicationStatus],
        max_length=100,
    )

    def questions_rendered(self, **kwargs):
        return markdown.render(self.questions, **kwargs)

    def answers_rendered(self, **kwargs):
        return markdown.render(self.answers, **kwargs)

    @transaction.atomic
    def accept(self, accepted_by):
        self.group.add_member(
            self.user,
            history_payload={
                'accepted_by': accepted_by.id,
                'application_date': self.created_at.isoformat(),
            }
        )
        self.status = GroupApplicationStatus.ACCEPTED.value
        self.save()

        notify_about_accepted_application(self)

    @transaction.atomic
    def decline(self, declined_by):
        History.objects.create(
            typus=HistoryTypus.GROUP_APPLICATION_DECLINED,
            group=self.group,
            users=[declined_by],
            payload={
                'applicant': self.user.id,
                'application_date': self.created_at.isoformat()
            }
        )
        self.status = GroupApplicationStatus.DECLINED.value
        self.save()

        notify_about_declined_application(self)

    @transaction.atomic
    def withdraw(self):
        self.status = GroupApplicationStatus.WITHDRAWN.value
        self.save()
