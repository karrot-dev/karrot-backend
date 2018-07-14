from datetime import timedelta
from enum import Enum

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models, transaction
from django.db.models import TextField, DateTimeField, QuerySet
from django.template.loader import render_to_string
from django.utils import timezone as tz
from timezone_field import TimeZoneField

from foodsaving.base.base_models import BaseModel, LocationModel
from foodsaving.conversations.models import ConversationMixin
from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils import markdown


class GroupStatus(Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    PLAYGROUND = 'playground'


class Group(BaseModel, LocationModel, ConversationMixin):
    name = models.CharField(max_length=settings.NAME_MAX_LENGTH, unique=True)
    description = models.TextField(blank=True)
    members = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='groups', through='GroupMembership')
    password = models.CharField(max_length=255, blank=True)  # TODO remove soon
    public_description = models.TextField(blank=True)
    application_questions = models.TextField(blank=True)
    status = models.CharField(
        default=GroupStatus.ACTIVE.value,
        choices=[(status.value, status.value) for status in GroupStatus],
        max_length=100,
    )
    sent_summary_up_to = DateTimeField(null=True)
    timezone = TimeZoneField(default='Europe/Berlin', null=True, blank=True)
    active_agreement = models.OneToOneField(
        'groups.Agreement',
        related_name='active_group',
        null=True,
        on_delete=models.SET_NULL
    )
    last_active_at = DateTimeField(default=tz.now)
    is_open = models.BooleanField(default=False)

    def __str__(self):
        return 'Group {}'.format(self.name)

    def add_member(self, user, history_payload=None):
        membership = GroupMembership.objects.create(group=self, user=user)
        History.objects.create(
            typus=HistoryTypus.GROUP_JOIN,
            group=self,
            users=[user, ],
            payload=history_payload
        )
        return membership

    def remove_member(self, user):
        History.objects.create(
            typus=HistoryTypus.GROUP_LEAVE,
            group=self,
            users=[user, ]
        )
        GroupMembership.objects.filter(group=self, user=user).delete()

    def is_member(self, user):
        return not user.is_anonymous and GroupMembership.objects.filter(group=self, user=user).exists()

    def is_member_with_role(self, user, role_name):
        return not user.is_anonymous and GroupMembership.objects.filter(group=self, user=user,
                                                                        roles__contains=[role_name]).exists()

    def is_playground(self):
        return self.status == GroupStatus.PLAYGROUND.value

    def accept_invite(self, user, invited_by, invited_at):
        self.add_member(user, history_payload={
            'invited_by': invited_by.id,
            'invited_at': invited_at.isoformat(),
            'invited_via': 'e-mail'
        })

    def refresh_active_status(self):
        self.last_active_at = tz.now()
        if self.status == GroupStatus.INACTIVE.value:
            self.status = GroupStatus.ACTIVE.value
        self.save()

    def has_recent_activity(self):
        return self.last_active_at >= tz.now() - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_GROUP_INACTIVE)

    def get_application_questions_or_default(self):
        if not self.application_questions:
            return render_to_string('default_application_questions.nopreview.jinja2', {
                'group': self,
            })
        return self.application_questions


class Agreement(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    title = TextField()
    content = TextField()
    users = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='agreements', through='UserAgreement')


class UserAgreement(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    agreement = models.ForeignKey(Agreement, on_delete=models.CASCADE)


class GroupNotificationType(object):
    WEEKLY_SUMMARY = 'weekly_summary'
    DAILY_PICKUP_NOTIFICATION = 'daily_pickup_notification'
    NEW_APPLICATION = 'new_application'


def get_default_notification_types():
    return [
        GroupNotificationType.WEEKLY_SUMMARY,
        GroupNotificationType.DAILY_PICKUP_NOTIFICATION,
        GroupNotificationType.NEW_APPLICATION,
    ]


class GroupMembershipQuerySet(QuerySet):

    def with_notification_type(self, type):
        return self.filter(notification_types__contains=[type])

    def active(self):
        return self.filter(inactive_at__isnull=True)


class GroupMembership(BaseModel):
    objects = GroupMembershipQuerySet.as_manager()

    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    roles = ArrayField(TextField(), default=list)
    lastseen_at = DateTimeField(default=tz.now)
    inactive_at = DateTimeField(null=True)
    notification_types = ArrayField(TextField(), default=get_default_notification_types)

    class Meta:
        db_table = 'groups_group_members'
        unique_together = (('group', 'user'),)

    def add_roles(self, roles):
        for role in roles:
            if role not in self.roles:
                self.roles.append(role)

    def remove_roles(self, roles):
        for role in roles:
            while role in self.roles:
                self.roles.remove(role)

    def add_notification_types(self, notification_types):
        for notification_type in notification_types:
            if notification_type not in self.notification_types:
                self.notification_types.append(notification_type)

    def remove_notification_types(self, notification_types):
        for notification_type in notification_types:
            while notification_type in self.notification_types:
                self.notification_types.remove(notification_type)


class GroupApplicationStatus(Enum):
    PENDING = 'pending'
    ACCEPTED = 'accepted'
    DECLINED = 'declined'
    WITHDRAWN = 'withdrawn'


class GroupApplication(BaseModel):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
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
        self.group.add_member(self.user, history_payload={
            'accepted_by': accepted_by.id,
            'application_date': self.created_at.isoformat(),
        })
        self.status = GroupApplicationStatus.ACCEPTED.value
        self.save()

        from foodsaving.groups import tasks
        tasks.notify_about_accepted_application(self)

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

        from foodsaving.groups import tasks
        tasks.notify_about_declined_application(self)

    @transaction.atomic
    def withdraw(self):
        self.status = GroupApplicationStatus.WITHDRAWN.value
        self.save()
