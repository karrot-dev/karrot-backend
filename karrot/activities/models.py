from datetime import timedelta
from enum import Enum

import pytz
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.utils.translation import gettext as _
from django.db import models
from django.db import transaction
from django.db.models import Avg, Count, DurationField, F, Q
from django.utils import timezone

from karrot.base.base_models import BaseModel, CustomDateTimeTZRange, CustomDateTimeRangeField, UpdatedAtMixin
from karrot.conversations.models import ConversationMixin
from karrot.history.models import History, HistoryTypus
from karrot.activities import stats
from karrot.activities.utils import match_activities_with_dates, rrule_between_dates_in_local_time
from karrot.places.models import PlaceStatus


class ActivityTypeStatus(Enum):
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class ActivityType(BaseModel, UpdatedAtMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='activity_types')
    name = models.CharField(max_length=80)
    name_is_translatable = models.BooleanField(default=True)
    colour = models.CharField(max_length=6)
    icon = models.CharField(max_length=32)
    feedback_icon = models.CharField(max_length=32)
    has_feedback = models.BooleanField(default=True)
    has_feedback_weight = models.BooleanField(default=True)
    status = models.CharField(
        default=ActivityTypeStatus.ACTIVE.value,
        choices=[(status.value, status.value) for status in ActivityTypeStatus],
        max_length=100,
    )

    class Meta:
        unique_together = ('group', 'name')

    def get_translated_name(self):
        # the translations are collected via activity_types.py
        return _(self.name) if self.name_is_translatable else self.name


class ActivitySeriesQuerySet(models.QuerySet):
    @transaction.atomic
    def update_activities(self):
        for series in self.filter(activity_type__status=ActivityTypeStatus.ACTIVE.value,
                                  place__status=PlaceStatus.ACTIVE.value):
            series.update_activities()

    def annotate_timezone(self):
        return self.annotate(timezone=F('place__group__timezone'))


class ActivitySeriesManager(models.Manager.from_queryset(ActivitySeriesQuerySet)):
    def get_queryset(self):
        return super().get_queryset().annotate_timezone()


class ActivitySeries(BaseModel):
    objects = ActivitySeriesManager()

    place = models.ForeignKey('places.Place', related_name='series', on_delete=models.CASCADE)
    max_participants = models.PositiveIntegerField(blank=True, null=True)
    rule = models.TextField()
    start_date = models.DateTimeField()
    description = models.TextField(blank=True)
    duration = DurationField(null=True)

    activity_type = models.ForeignKey(
        ActivityType,
        related_name='activity_series',
        on_delete=models.CASCADE,
    )

    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='changed_series',
        null=True,
    )

    def create_activity(self, date):
        return self.activities.create(
            activity_type=self.activity_type,
            date=CustomDateTimeTZRange(date, date + (self.duration or default_duration)),
            has_duration=self.duration is not None,
            max_participants=self.max_participants,
            series=self,
            place=self.place,
            description=self.description,
            last_changed_by=self.last_changed_by,
        )

    def period_start(self):
        # shift start time slightly into future to avoid activities which are only valid for very short time
        return timezone.now() + relativedelta(minutes=5)

    def dates(self):
        return rrule_between_dates_in_local_time(
            rule=self.rule,
            dtstart=self.start_date,
            tz=self.get_timezone(),
            period_start=self.period_start(),
            period_duration=relativedelta(weeks=self.place.weeks_in_advance)
        )

    def get_timezone(self):
        value = self.timezone if hasattr(self, 'timezone') else self.place.group.timezone
        return pytz.timezone(value) if isinstance(value, str) else value

    def get_matched_activities(self):
        return match_activities_with_dates(
            activities=self.activities.order_by('date').filter(date__startswith__gt=self.period_start()),
            new_dates=self.dates(),
        )

    def update_activities(self):
        """
        create new activities and delete empty activities that don't match series
        """

        for activity, date in self.get_matched_activities():
            if not activity:
                self.create_activity(date)
            elif not date:
                if activity.participants.count() < 1:
                    activity.delete()

    def __str__(self):
        return 'ActivitySeries {} - {}'.format(self.rule, self.place)

    def save(self, *args, **kwargs):
        old = type(self).objects.get(pk=self.pk) if self.pk else None

        super().save(*args, **kwargs)

        if not old or old.start_date != self.start_date or old.rule != self.rule:
            self.update_activities()

        if old:
            description_changed = old.description != self.description
            max_participants_changed = old.max_participants != self.max_participants
            duration_changed = old.duration != self.duration
            if description_changed or max_participants_changed or duration_changed:
                for activity in self.activities.upcoming():
                    if description_changed and old.description == activity.description:
                        activity.description = self.description
                    if max_participants_changed and old.max_participants == activity.max_participants:
                        activity.max_participants = self.max_participants
                    if duration_changed:
                        if self.duration:
                            activity.has_duration = True
                            activity.date = CustomDateTimeTZRange(
                                activity.date.start, activity.date.start + self.duration
                            )
                        else:
                            activity.has_duration = False
                            activity.date = CustomDateTimeTZRange(
                                activity.date.start, activity.date.start + default_duration
                            )
                    activity.save()

    def delete(self, **kwargs):
        self.rule = str(rrulestr(self.rule).replace(dtstart=self.start_date, until=timezone.now()))
        self.update_activities()
        return super().delete()


class ActivityQuerySet(models.QuerySet):
    def _feedback_possible_q(self, user):
        return Q(is_done=True) \
               & Q(activity_type__has_feedback=True) \
               & Q(date__endswith__gte=timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)) \
               & Q(participants=user) \
               & ~Q(feedback__given_by=user) \
               & Q(activityparticipant__feedback_dismissed=False)

    def only_feedback_possible(self, user):
        return self.filter(self._feedback_possible_q(user))

    def exclude_feedback_possible(self, user):
        return self.filter(~self._feedback_possible_q(user))

    def annotate_num_participants(self):
        return self.annotate(num_participants=Count('participants'))

    def annotate_timezone(self):
        return self.annotate(timezone=F('place__group__timezone'))

    def annotate_feedback_weight(self):
        return self.annotate(feedback_weight=Avg('feedback__weight'))

    def exclude_disabled(self):
        return self.filter(is_disabled=False)

    def in_group(self, group):
        return self.filter(place__group=group)

    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.ACTIVITY_DUE_SOON_HOURS)
        return self.exclude_disabled().filter(date__startswith__gt=timezone.now(), date__startswith__lt=in_some_hours)

    def missed(self):
        return self.exclude_disabled().filter(date__startswith__lt=timezone.now(), participants=None)

    def done(self):
        return self.exclude_disabled().filter(date__startswith__lt=timezone.now()).exclude(participants=None)

    def done_not_full(self):
        return self.exclude_disabled() \
            .annotate(participant_count=Count('participants')) \
            .filter(date__startswith__lt=timezone.now(), participant_count__lt=F('max_participants'))

    def upcoming(self):
        return self.filter(date__startswith__gt=timezone.now())

    @transaction.atomic
    def process_finished_activities(self):
        """
        find all activities that are in the past and didn't get processed yet
        add them to history and mark as processed
        """
        for activity in self.exclude_disabled().filter(
                is_done=False,
                date__startswith__lt=timezone.now(),
        ):
            if not activity.place.is_active():
                # Make sure we don't process this activity again, even if the place gets active in future
                activity.is_disabled = True
                activity.save()
                continue

            payload = {}
            payload['activity_date'] = activity.id
            if activity.series:
                payload['series'] = activity.series.id
            if activity.max_participants:
                payload['max_participants'] = activity.max_participants
            if activity.participants.count() == 0:
                stats.activity_missed(activity)
                History.objects.create(
                    typus=HistoryTypus.ACTIVITY_MISSED,
                    group=activity.place.group,
                    place=activity.place,
                    activity=activity,
                    date=activity.date.start,
                    payload=payload,
                )
            else:
                stats.activity_done(activity)
                History.objects.create(
                    typus=HistoryTypus.ACTIVITY_DONE,
                    group=activity.place.group,
                    place=activity.place,
                    activity=activity,
                    users=activity.participants.all(),
                    date=activity.date.start,
                    payload=payload,
                )

            activity.is_done = True
            activity.save()


class ActivityManager(models.Manager.from_queryset(ActivityQuerySet)):
    def get_queryset(self):
        return super().get_queryset().annotate_timezone()


default_duration = timedelta(minutes=30)


def default_activity_date_range():
    return CustomDateTimeTZRange(timezone.now(), timezone.now() + default_duration)


def to_range(date, **kwargs):
    duration = timedelta(**kwargs) if kwargs else default_duration
    return CustomDateTimeTZRange(date, date + duration)


class Activity(BaseModel, ConversationMixin):
    objects = ActivityManager()

    class Meta:
        ordering = ['date']

    activity_type = models.ForeignKey(
        ActivityType,
        related_name='activities',
        on_delete=models.CASCADE,
    )

    series = models.ForeignKey(
        'ActivitySeries',
        related_name='activities',
        on_delete=models.SET_NULL,
        null=True,
    )
    place = models.ForeignKey(
        'places.Place',
        related_name='activities',
        on_delete=models.CASCADE,
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='activities',
        through='ActivityParticipant',
        through_fields=('activity', 'user')
    )
    feedback_given_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='feedback_about_activities',
        through='Feedback',
        through_fields=('about', 'given_by')
    )
    date = CustomDateTimeRangeField(default=default_activity_date_range)
    has_duration = models.BooleanField(default=False)

    description = models.TextField(blank=True)
    max_participants = models.PositiveIntegerField(null=True)
    is_disabled = models.BooleanField(default=False)
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name='activities_changed',
        on_delete=models.SET_NULL,
    )

    is_done = models.BooleanField(default=False)

    @property
    def group(self):
        return self.place.group

    @property
    def ended_at(self):
        if self.is_upcoming():
            return None
        return self.date.end

    def __str__(self):
        return 'Activity {} - {}'.format(self.date.start, self.place)

    def get_timezone(self):
        value = self.timezone if hasattr(self, 'timezone') else self.group.timezone
        return pytz.timezone(value) if isinstance(value, str) else value

    def feedback_due(self):
        if not self.activity_type.has_feedback:
            return None
        due = self.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)
        return due.astimezone(self.get_timezone())

    def is_upcoming(self):
        return self.date.start > timezone.now()

    def is_full(self):
        if not self.max_participants:
            return False
        return self.participants.count() >= self.max_participants

    def is_participant(self, user):
        return self.participants.filter(id=user.id).exists()

    def is_empty(self):
        return self.participants.count() == 0

    def is_recent(self):
        return self.date.start >= timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    def empty_participants_count(self):
        return max(0, self.max_participants - self.participants.count())

    def add_participant(self, user):
        participant, _ = ActivityParticipant.objects.get_or_create(
            activity=self,
            user=user,
        )
        return participant

    def remove_participant(self, user):
        ActivityParticipant.objects.filter(
            activity=self,
            user=user,
        ).delete()

    def dismiss_feedback(self, user):
        activity_participant = ActivityParticipant.objects.get(
            activity=self,
            user=user,
        )
        activity_participant.feedback_dismissed = True
        # TODO Is this save necessary?
        activity_participant.save()

    def save(self, *args, **kwargs):
        if not self.has_duration:
            # reset duration to default if activity has no explicit duration
            start = self.date.start
            self.date = CustomDateTimeTZRange(start, start + default_duration)

        super().save(*args, **kwargs)


class ActivityParticipant(BaseModel):
    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )
    feedback_dismissed = models.BooleanField(default=False)
    reminder_task_id = models.TextField(null=True)  # stores a huey task id

    class Meta:
        db_table = 'activities_activity_participants'
        unique_together = (('activity', 'user'), )
        ordering = ['created_at']


class Feedback(BaseModel):
    given_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='feedback')
    about = models.ForeignKey('Activity', on_delete=models.CASCADE)
    weight = models.FloatField(
        blank=True, null=True, validators=[MinValueValidator(-0.01),
                                           MaxValueValidator(10000.0)]
    )
    comment = models.CharField(max_length=settings.DESCRIPTION_MAX_LENGTH, blank=True)

    # just to store legacy values for when feedback_as_sum was False on activities... null otherwise
    # I guess can remove it after a while...
    weight_for_average = models.FloatField(null=True)

    class Meta:
        unique_together = ('about', 'given_by')
