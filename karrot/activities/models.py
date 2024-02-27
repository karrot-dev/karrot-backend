import uuid
from datetime import timedelta

import pytz
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GistIndex
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.db.models import (
    CheckConstraint,
    Count,
    DurationField,
    Exists,
    ExpressionWrapper,
    F,
    OuterRef,
    Q,
    Sum,
    TextField,
)
from django.utils import timezone
from django.utils.translation import gettext as _
from versatileimagefield.fields import VersatileImageField
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from karrot.activities import stats
from karrot.activities.utils import match_activities_with_dates, rrule_between_dates_in_local_time
from karrot.base.base_models import (
    BaseModel,
    CustomDateTimeRangeField,
    CustomDateTimeTZRange,
    NicelyFormattedModel,
    UpdatedAtMixin,
    UploadToUUID,
)
from karrot.conversations.models import ConversationMixin
from karrot.groups.roles import GROUP_MEMBER
from karrot.history.models import History, HistoryTypus


class ActivityType(BaseModel, UpdatedAtMixin):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE, related_name="activity_types")
    name = models.CharField(max_length=80)
    name_is_translatable = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    colour = models.CharField(max_length=6)
    icon = models.CharField(max_length=100)
    feedback_icon = models.CharField(max_length=100)
    has_feedback = models.BooleanField(default=True)
    has_feedback_weight = models.BooleanField(default=True)
    archived_at = models.DateTimeField(null=True)

    class Meta:
        unique_together = ("group", "name")

    def get_translated_name(self):
        # the translations are collected via activity_types.py
        return _(self.name) if self.name_is_translatable else self.name

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None


class ActivitySeriesQuerySet(models.QuerySet):
    @transaction.atomic
    def update_activities(self):
        for series in self.filter(activity_type__archived_at__isnull=True, place__archived_at__isnull=True):
            series.update_activities()

    def annotate_timezone(self):
        return self.annotate(timezone=F("place__group__timezone"))


class ActivitySeriesManager(models.Manager.from_queryset(ActivitySeriesQuerySet)):
    def get_queryset(self):
        return super().get_queryset().annotate_timezone()


class ActivitySeries(BaseModel):
    objects = ActivitySeriesManager()

    place = models.ForeignKey("places.Place", related_name="series", on_delete=models.CASCADE)
    rule = models.TextField()
    start_date = models.DateTimeField()
    description = models.TextField(blank=True)
    duration = DurationField(null=True)
    is_public = models.BooleanField(default=False)

    activity_type = models.ForeignKey(
        ActivityType,
        related_name="activity_series",
        on_delete=models.CASCADE,
    )

    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name="changed_series",
        null=True,
    )

    banner_image = VersatileImageField(
        "BannerImage",
        upload_to=UploadToUUID("activity_series__banner_images"),
        null=True,
    )

    def create_activity(self, date):
        activity = self.activities.create(
            activity_type=self.activity_type,
            date=CustomDateTimeTZRange(date, date + (self.duration or default_duration)),
            has_duration=self.duration is not None,
            series=self,
            is_public=self.is_public,
            public_id=uuid.uuid4() if self.is_public else None,
            place=self.place,
            description=self.description,
            last_changed_by=self.last_changed_by,
        )
        for participant_type in self.participant_types.all():
            activity.participant_types.create(
                role=participant_type.role,
                max_participants=participant_type.max_participants,
                description=participant_type.description,
                series_participant_type=participant_type,
            )
        return activity

    def period_start(self):
        # shift start time slightly into future to avoid activities which are only valid for very short time
        return timezone.now() + relativedelta(minutes=5)

    def dates(self):
        return rrule_between_dates_in_local_time(
            rule=self.rule,
            dtstart=self.start_date,
            tz=self.get_timezone(),
            period_start=self.period_start(),
            period_duration=relativedelta(weeks=self.place.weeks_in_advance),
        )

    def get_timezone(self):
        value = self.timezone if hasattr(self, "timezone") else self.place.group.timezone
        return pytz.timezone(value) if isinstance(value, str) else value

    def get_matched_activities(self):
        return match_activities_with_dates(
            activities=self.activities.order_by("date").filter(date__startswith__gt=self.period_start()),
            new_dates=self.dates(),
        )

    def old(self):
        return type(self).objects.get(pk=self.pk) if self.pk else None

    def update_activities(self):
        for activity, date in self.get_matched_activities():
            if not activity:
                self.create_activity(date)
            elif not date:
                if activity.participants.count() < 1:
                    activity.delete()

    def __str__(self):
        return f"ActivitySeries {self.rule} - {self.place}"

    def delete_banner_image(self):
        if self.banner_image.name is None:
            return
        # Deletes Image Renditions
        self.banner_image.delete_all_created_images()
        # Deletes Original Image
        self.banner_image.delete(save=False)

    def delete(self, **kwargs):
        self.rule = str(rrulestr(self.rule).replace(dtstart=self.start_date, until=timezone.now()))
        self.update_activities()
        return super().delete()


class ActivityQuerySet(models.QuerySet):
    def _feedback_possible_q(self, user):
        return (
            Q(has_started=True)
            & Q(activity_type__has_feedback=True)
            & Q(date__endswith__gte=timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS))
            & Q(participants=user)
            & ~Q(feedback__given_by=user)
            & Q(activityparticipant__feedback_dismissed=False)
        )

    def only_feedback_possible(self, user):
        return self.filter(self._feedback_possible_q(user))

    def exclude_feedback_possible(self, user):
        return self.filter(~self._feedback_possible_q(user))

    def annotate_num_participants(self):
        return self.annotate(num_participants=Count("activityparticipant"))

    def alias_num_participants(self):
        return self.alias(num_participants=Count("activityparticipant"))

    def annotate_timezone(self):
        return self.annotate(timezone=F("place__group__timezone"))

    def annotate_feedback_weight(self):
        return self.annotate(feedback_weight=Sum("feedback__weight"))

    def annotate_feedback_count(self):
        return self.annotate(feedback_count=Count("feedback"))

    def exclude_disabled(self):
        return self.filter(is_disabled=False)

    def in_group(self, group):
        return self.filter(place__group=group)

    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.ACTIVITY_DUE_SOON_HOURS)
        return self.exclude_disabled().filter(date__startswith__gt=timezone.now(), date__startswith__lt=in_some_hours)

    def missed(self):
        return self.exclude_disabled().filter(date__endswith__lt=timezone.now(), participants=None)

    def done(self):
        return (
            self.exclude_disabled()
            .filter(date__endswith__lt=timezone.now())
            .annotate_num_participants()
            .filter(num_participants__gt=0)
        )

    def with_free_slots(self, user):
        participant_types_with_free_slots = (
            ParticipantType.objects.filter(activity=OuterRef("id"))
            # Ones that have some capacity still
            .alias_num_participants()
            .filter(num_participants__lt=F("max_participants"))
        )

        if user:
            # We have a user!
            # Make sure their roles in the appropriate group match up
            participant_types_with_free_slots = participant_types_with_free_slots.alias(
                # (It gets confused without the ExpressionWrapper ... :/)
                roles=ExpressionWrapper(
                    # Use an OuterRef so we can refer to the membership we have
                    # already selected in the outer query
                    OuterRef("place__group__groupmembership__roles"),
                    output_field=ArrayField(TextField()),
                )
            ).filter(roles__contains=[F("role")])

        activities = (
            self.exclude_disabled()
            .alias(has_free_slot=Exists(participant_types_with_free_slots))
            .filter(has_free_slot=True)
            .distinct()
        )

        return activities

    def empty(self):
        return self.exclude_disabled().alias_num_participants().filter(num_participants=0)

    def with_participant(self, user):
        return self.filter(participants=user)

    def upcoming(self):
        return self.filter(date__startswith__gt=timezone.now())

    def is_public(self):
        return self.filter(is_public=True)

    @transaction.atomic
    def process_activities(self):
        """Process activities that have started OR ended

        We process them at two moments:

        after started
        We don't do anything here, but receivers will

        after ended
        This is when we add the history
        Important to do that at the end, so that anybody that joined
        after it started is still counted in the history.
        """
        now = timezone.now()

        for activity in self.exclude_disabled().filter(
            has_started=False,
            date__startswith__lt=now,
        ):
            if activity.place.is_archived:
                # Make sure we don't process this activity again, even if the place gets active in future
                activity.is_disabled = True
                activity.save()
                continue

            activity.has_started = True
            activity.save()

        for activity in self.exclude_disabled().filter(
            is_done=False,
            date__endswith__lt=now,
        ):
            if activity.place.is_archived:
                # Make sure we don't process this activity again, even if the place gets active in future
                activity.is_disabled = True
                activity.save()
                continue

            payload = {}
            payload["activity_date"] = activity.id
            if activity.series:
                payload["series"] = activity.series.id
            max_participants = activity.get_total_max_participants()
            if max_participants:
                payload["max_participants"] = max_participants
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
        ordering = ["date"]
        indexes = [GistIndex(fields=["date"])]
        constraints = [
            CheckConstraint(
                # if it's public it must have a public_id
                check=Q(is_public=False) | Q(public_id__isnull=False),
                name="public_activities_must_have_public_id",
            )
        ]

    activity_type = models.ForeignKey(
        ActivityType,
        related_name="activities",
        on_delete=models.CASCADE,
    )

    series = models.ForeignKey(
        "ActivitySeries",
        related_name="activities",
        on_delete=models.SET_NULL,
        null=True,
    )
    place = models.ForeignKey(
        "places.Place",
        related_name="activities",
        on_delete=models.CASCADE,
    )
    participants = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="activities",
        through="ActivityParticipant",
        through_fields=("activity", "user"),
    )
    feedback_given_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name="feedback_about_activities",
        through="Feedback",
        through_fields=("about", "given_by"),
    )
    date = CustomDateTimeRangeField(default=default_activity_date_range)
    has_duration = models.BooleanField(default=False)

    is_public = models.BooleanField(default=False)
    public_id = models.UUIDField(null=True, unique=True)

    description = models.TextField(blank=True)
    is_disabled = models.BooleanField(default=False)
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name="activities_changed",
        on_delete=models.SET_NULL,
    )

    has_started = models.BooleanField(default=False)
    is_done = models.BooleanField(default=False)

    banner_image = VersatileImageField(
        "BannerImage",
        upload_to=UploadToUUID("activity__banner_images"),
        null=True,
    )

    @property
    def group(self):
        return self.place.group

    @property
    def ended_at(self):
        if self.is_not_past():
            return None
        return self.date.end

    def __str__(self):
        return f"Activity {self.date.start} - {self.place}"

    def get_timezone(self):
        value = self.timezone if hasattr(self, "timezone") else self.group.timezone
        return pytz.timezone(value) if isinstance(value, str) else value

    def feedback_due(self):
        if not self.activity_type.has_feedback:
            return None
        due = self.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)
        return due.astimezone(self.get_timezone())

    def is_upcoming(self):
        return self.date.start > timezone.now()

    def is_past(self):
        return self.date.end < timezone.now()

    def is_not_past(self):
        return not self.is_past()

    def is_participant(self, user):
        return self.participants.filter(id=user.id).exists()

    def is_recent(self):
        return self.date.start >= timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    def get_total_max_participants(self):
        values = [entry.max_participants for entry in self.participant_types.all()]
        if None in values:
            return None
        return sum(values)

    def add_participant(self, user, participant_type=None):
        if not participant_type:
            # make it work without passing participant_type for the simple case
            if self.participant_types.count() > 1:
                raise Exception("must pass participant_type as >1")
            participant_type = self.participant_types.first()

        # this assumes the users group roles have already been checked
        participant, _ = ActivityParticipant.objects.get_or_create(
            activity=self,
            user=user,
            participant_type=participant_type,
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
        activity_participant.save()

    def delete_banner_image(self):
        if self.banner_image.name is None:
            return
        # Deletes Image Renditions
        self.banner_image.delete_all_created_images()
        # Deletes Original Image
        self.banner_image.delete(save=False)

    def save(self, *args, **kwargs):
        if not self.has_duration:
            # reset duration to default if activity has no explicit duration
            start = self.date.start
            self.date = CustomDateTimeTZRange(start, start + default_duration)

        super().save(*args, **kwargs)


class SeriesParticipantType(BaseModel):
    class Meta:
        ordering = ["id"]

    activity_series = models.ForeignKey(
        ActivitySeries,
        on_delete=models.CASCADE,
        related_name="participant_types",
    )
    description = models.TextField(blank=True)
    max_participants = models.PositiveIntegerField(null=True)
    role = models.CharField(max_length=100, default=GROUP_MEMBER)


class ParticipantTypeQuerySet(models.QuerySet):
    def annotate_num_participants(self):
        return self.annotate(num_participants=Count("participants"))

    def alias_num_participants(self):
        return self.alias(num_participants=Count("participants"))


class ParticipantTypeManager(models.Manager.from_queryset(ParticipantTypeQuerySet)):
    pass


class ParticipantType(BaseModel):
    objects = ParticipantTypeManager()

    class Meta:
        ordering = ["id"]

    activity = models.ForeignKey(
        Activity,
        on_delete=models.CASCADE,
        related_name="participant_types",
    )
    series_participant_type = models.ForeignKey(
        SeriesParticipantType,
        on_delete=models.SET_NULL,
        related_name="participant_types",
        null=True,
    )
    description = models.TextField(blank=True)
    max_participants = models.PositiveIntegerField(null=True)
    role = models.CharField(max_length=100, default=GROUP_MEMBER)

    def is_full(self):
        if not self.max_participants:
            return False
        return self.activity.activityparticipant_set.filter(participant_type=self).count() >= self.max_participants


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
    participant_type = models.ForeignKey(
        ParticipantType,
        on_delete=models.CASCADE,
        null=False,
        related_name="participants",
    )

    class Meta:
        db_table = "activities_activity_participants"
        unique_together = (("activity", "user"),)
        ordering = ["created_at"]


class Feedback(BaseModel):
    given_by = models.ForeignKey("users.User", on_delete=models.CASCADE, related_name="feedback")
    about = models.ForeignKey("Activity", on_delete=models.CASCADE)
    weight = models.FloatField(blank=True, null=True, validators=[MinValueValidator(-0.01), MaxValueValidator(10000.0)])
    comment = models.CharField(max_length=settings.DESCRIPTION_MAX_LENGTH, blank=True)

    # just to store legacy values for when feedback_as_sum was False on activities... null otherwise
    # I guess can remove it after a while...
    weight_for_average = models.FloatField(null=True)

    class Meta:
        unique_together = ("about", "given_by")


class FeedbackNoShow(BaseModel):
    feedback = models.ForeignKey(
        Feedback,
        on_delete=models.CASCADE,
        related_name="no_shows",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )


class ICSAuthToken(NicelyFormattedModel):
    token = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField("users.User", on_delete=models.CASCADE)
    created_at = models.DateTimeField(default=timezone.now)


def create_activity_banner_image_warmer(instance_or_queryset, *, verbose=False):
    return VersatileImageFieldWarmer(
        instance_or_queryset=instance_or_queryset,
        rendition_key_set="activity_banner_image",
        image_attr="banner_image",
        verbose=verbose,
    )
