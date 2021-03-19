from datetime import timedelta
from dirtyfields import DirtyFieldsMixin
from enum import Enum

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models
from django.db.models import TextField, DateTimeField, QuerySet, Count, Q, F
from django.db.models.manager import BaseManager
from django.template.loader import render_to_string
from django.utils import timezone as tz, timezone
from timezone_field import TimeZoneField
from versatileimagefield.fields import VersatileImageField

from karrot.activities.activity_types import default_activity_types
from karrot.base.base_models import BaseModel, LocationModel
from karrot.conversations.models import ConversationMixin
from karrot.history.models import History, HistoryTypus
from karrot.activities.models import Activity, ActivityType
from karrot.places.models import PlaceStatus, PlaceType
from karrot.places.place_statuses import default_place_statuses
from karrot.places.place_types import default_place_types
from karrot.utils import markdown
from karrot.groups import roles, themes


def default_group_features():
    return ['offers']


class GroupStatus(Enum):
    ACTIVE = 'active'
    INACTIVE = 'inactive'
    PLAYGROUND = 'playground'


class GroupQuerySet(models.QuerySet):
    def user_is_editor(self, user):
        return self.filter(
            groupmembership__roles__contains=[roles.GROUP_EDITOR],
            groupmembership__user=user,
        )

    def annotate_yesterdays_member_count(self):
        one_day_ago = timezone.now() - relativedelta(days=1)
        return self.annotate(
            _yesterdays_member_count=Count(
                'groupmembership',
                filter=Q(
                    groupmembership__created_at__lte=one_day_ago,
                    groupmembership__inactive_at__isnull=True,
                )
            )
        )


class GroupManager(BaseManager.from_queryset(GroupQuerySet)):
    def create(self, *args, **kwargs):
        kwargs['theme'] = kwargs.get('theme', settings.GROUP_THEME_DEFAULT.value)
        return super(GroupManager, self).create(*args, **kwargs)


class Group(BaseModel, LocationModel, ConversationMixin, DirtyFieldsMixin):
    objects = GroupManager()

    name = models.CharField(max_length=settings.NAME_MAX_LENGTH, unique=True)
    description = models.TextField(blank=True)
    welcome_message = models.TextField(blank=True)
    members = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='groups',
        through='GroupMembership',
        through_fields=('group', 'user'),
    )
    public_description = models.TextField(blank=True)
    application_questions = models.TextField(blank=True)
    status = models.CharField(
        default=GroupStatus.ACTIVE.value,
        choices=[(status.value, status.value) for status in GroupStatus],
        max_length=100,
    )
    theme = models.TextField(
        # default is set by GroupManager
        choices=[(theme.value, theme.value) for theme in themes.GroupTheme],
    )
    sent_summary_up_to = DateTimeField(null=True)
    timezone = TimeZoneField(default='Europe/Berlin', null=True, blank=True)
    active_agreement = models.OneToOneField(
        'groups.Agreement',
        related_name='active_group',
        null=True,
        on_delete=models.SET_NULL,
    )
    last_active_at = DateTimeField(default=tz.now)
    is_open = models.BooleanField(default=False)
    photo = VersatileImageField(
        'Group Photo',
        upload_to='group_photos',
        null=True,
    )
    features = ArrayField(TextField(), default=default_group_features)

    @property
    def group(self):
        return self

    @property
    def conversation_supports_threads(self):
        return True

    def __str__(self):
        return 'Group {}'.format(self.name)

    def add_member(self, user, added_by=None, history_payload=None):
        membership = GroupMembership.objects.create(
            group=self,
            user=user,
            added_by=added_by,
        )
        History.objects.create(
            typus=HistoryTypus.GROUP_JOIN,
            group=self,
            users=[user],
            payload=history_payload,
        )
        return membership

    def remove_member(self, user):
        History.objects.create(typus=HistoryTypus.GROUP_LEAVE, group=self, users=[user])
        GroupMembership.objects.filter(group=self, user=user).delete()

    def is_member(self, user):
        return not user.is_anonymous and GroupMembership.objects.filter(group=self, user=user).exists()

    def is_editor(self, user):
        return self.is_member_with_role(user, roles.GROUP_EDITOR)

    def is_member_with_role(self, user, role_name):
        return not user.is_anonymous and GroupMembership.objects.filter(
            group=self, user=user, roles__contains=[role_name]
        ).exists()

    def is_playground(self):
        return self.status == GroupStatus.PLAYGROUND.value

    def accept_invite(self, user, invited_by, invited_at):
        self.add_member(
            user,
            added_by=invited_by,
            history_payload={
                'invited_by': invited_by.id,
                'invited_at': invited_at.isoformat(),
                'invited_via': 'e-mail'
            }
        )

    def refresh_active_status(self):
        self.last_active_at = tz.now()
        if self.status == GroupStatus.INACTIVE.value:
            self.status = GroupStatus.ACTIVE.value
        self.save()

    def has_recent_activity(self):
        return self.last_active_at >= tz.now() - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_GROUP_INACTIVE)

    def get_application_questions_or_default(self):
        return self.application_questions or self.application_questions_default()

    def application_questions_default(self):
        return render_to_string('default_application_questions.nopreview.jinja2')

    def trust_threshold_for_newcomer(self):
        count = getattr(self, '_yesterdays_member_count', None)
        if count is None:
            one_day_ago = timezone.now() - relativedelta(days=1)
            count = self.groupmembership_set.active().filter(created_at__lte=one_day_ago).count()
        dynamic_threshold = max(1, count // 2)
        trust_threshold = min(settings.GROUP_EDITOR_TRUST_MAX_THRESHOLD, dynamic_threshold)
        return trust_threshold

    def delete_photo(self):
        if self.photo.name is None:
            return
        # Deletes Image Renditions
        self.photo.delete_all_created_images()
        # Deletes Original Image
        self.photo.delete(save=False)

    def welcome_message_rendered(self, **kwargs):
        return markdown.render(self.welcome_message, **kwargs)

    def create_default_types(self):

        # activity types
        for name, options in default_activity_types.items():
            ActivityType.objects.get_or_create(name=name, group=self, defaults=options)

        # place types
        for name, options in default_place_types.items():
            PlaceType.objects.get_or_create(name=name, group=self, defaults=options)

        # place statuses
        for name, options in default_place_statuses.items():
            PlaceStatus.objects.get_or_create(name=name, group=self, defaults=options)


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
    DAILY_ACTIVITY_NOTIFICATION = 'daily_activity_notification'
    NEW_APPLICATION = 'new_application'
    CONFLICT_RESOLUTION = 'conflict_resolution'
    NEW_OFFER = 'new_offer'


def get_default_notification_types():
    return [
        GroupNotificationType.WEEKLY_SUMMARY,
        GroupNotificationType.DAILY_ACTIVITY_NOTIFICATION,
        GroupNotificationType.CONFLICT_RESOLUTION,
    ]


class GroupMembershipQuerySet(QuerySet):
    def with_notification_type(self, type):
        return self.filter(notification_types__contains=[type])

    def with_role(self, role):
        return self.filter(roles__contains=[role])

    def without_role(self, role):
        return self.exclude(roles__contains=[role])

    def active(self):
        return self.filter(inactive_at__isnull=True)

    def active_within(self, **kwargs):
        now = timezone.now()
        return self.filter(lastseen_at__gte=now - relativedelta(**kwargs))

    def activity_active_within(self, **kwargs):
        now = timezone.now()
        return self.filter(
            user__activities__in=Activity.objects.exclude_disabled().filter(
                date__startswith__lt=now,
                date__startswith__gte=now - relativedelta(**kwargs),
            ),
            user__activities__place__group=F('group'),
        ).distinct()

    def editors(self):
        return self.with_role(roles.GROUP_EDITOR)

    def newcomers(self):
        return self.without_role(roles.GROUP_EDITOR)

    def exclude_playgrounds(self):
        return self.exclude(group__status=GroupStatus.PLAYGROUND)


class GroupMembership(BaseModel, DirtyFieldsMixin):
    objects = GroupMembershipQuerySet.as_manager()

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='groupmembership_added',
    )
    trusted_by = models.ManyToManyField(settings.AUTH_USER_MODEL, related_name='membership', through='Trust')
    roles = ArrayField(TextField(), default=list)
    lastseen_at = DateTimeField(default=tz.now)
    inactive_at = DateTimeField(null=True)
    notification_types = ArrayField(TextField(), default=get_default_notification_types)
    removal_notification_at = DateTimeField(null=True)

    class Meta:
        db_table = 'groups_group_members'
        unique_together = (('group', 'user'), )

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


class Trust(BaseModel):
    membership = models.ForeignKey('groups.GroupMembership', on_delete=models.CASCADE)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trust_given')

    class Meta:
        unique_together = (('membership', 'given_by'), )
