import dateutil
from datetime import timedelta
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from foodsaving.base.base_models import BaseModel, CustomDateTimeTZRange, CustomDateTimeRangeField
from foodsaving.conversations.models import ConversationMixin
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups import stats
from foodsaving.pickups.utils import match_pickups_with_dates, rrule_between_dates_in_local_time
from foodsaving.stores.models import StoreStatus


class PickupDateSeriesQuerySet(models.QuerySet):
    @transaction.atomic
    def update_pickups(self):
        for series in self.filter(store__status=StoreStatus.ACTIVE.value):
            series.update_pickups()


class PickupDateSeries(BaseModel):
    objects = PickupDateSeriesQuerySet.as_manager()

    store = models.ForeignKey('stores.Store', related_name='series', on_delete=models.CASCADE)
    max_collectors = models.PositiveIntegerField(blank=True, null=True)
    rule = models.TextField()
    start_date = models.DateTimeField()
    description = models.TextField(blank=True)

    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        related_name='changed_series',
        null=True,
    )

    def create_pickup(self, date):
        return self.pickup_dates.create(
            date=CustomDateTimeTZRange(date, date + timedelta(minutes=30)),  # TODO: make duration part of series?
            max_collectors=self.max_collectors,
            series=self,
            store=self.store,
            description=self.description,
            last_changed_by=self.last_changed_by,
        )

    def period_start(self):
        # shift start time slightly into future to avoid pickup dates which are only valid for very short time
        return timezone.now() + relativedelta(minutes=5)

    def dates(self):
        return rrule_between_dates_in_local_time(
            rule=self.rule,
            dtstart=self.start_date,
            tz=self.store.group.timezone,
            period_start=self.period_start(),
            period_duration=relativedelta(weeks=self.store.weeks_in_advance)
        )

    def get_matched_pickups(self):
        return match_pickups_with_dates(
            pickups=self.pickup_dates.order_by('date').filter(date__startswith__gt=self.period_start()),
            new_dates=self.dates(),
        )

    def update_pickups(self):
        """
        create new pickups and delete empty pickups that don't match series
        """

        for pickup, date in self.get_matched_pickups():
            if not pickup:
                self.create_pickup(date)
            elif not date:
                if pickup.collectors.count() < 1:
                    pickup.delete()

    def __str__(self):
        return 'PickupDateSeries {} - {}'.format(self.rule, self.store)

    def save(self, *args, **kwargs):
        old = type(self).objects.get(pk=self.pk) if self.pk else None

        super().save(*args, **kwargs)

        if not old or old.start_date != self.start_date or old.rule != self.rule:
            self.update_pickups()

        if old:
            description_changed = old.description != self.description
            max_collectors_changed = old.max_collectors != self.max_collectors
            if description_changed or max_collectors_changed:
                for pickup in self.pickup_dates.upcoming():
                    if description_changed and old.description == pickup.description:
                        pickup.description = self.description
                    if max_collectors_changed and old.max_collectors == pickup.max_collectors:
                        pickup.max_collectors = self.max_collectors
                    pickup.save()

    def delete(self, **kwargs):
        self.rule = str(dateutil.rrule.rrulestr(self.rule).replace(dtstart=self.start_date, until=timezone.now()))
        self.update_pickups()
        return super().delete()


class PickupDateQuerySet(models.QuerySet):
    def _feedback_possible_q(self, user):
        return Q(feedback_possible=True) \
               & Q(date__endswith__gte=timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)) \
               & Q(collectors=user) \
               & ~Q(feedback__given_by=user)

    def only_feedback_possible(self, user):
        return self.filter(self._feedback_possible_q(user))

    def exclude_feedback_possible(self, user):
        return self.filter(~self._feedback_possible_q(user))

    def annotate_num_collectors(self):
        return self.annotate(num_collectors=Count('collectors'))

    def exclude_disabled(self):
        return self.filter(is_disabled=False)

    def in_group(self, group):
        return self.filter(store__group=group)

    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.PICKUPDATE_DUE_SOON_HOURS)
        return self.exclude_disabled().filter(date__startswith__gt=timezone.now(), date__startswith__lt=in_some_hours)

    def missed(self):
        return self.exclude_disabled().filter(date__startswith__lt=timezone.now(), collectors=None)

    def done(self):
        return self.exclude_disabled().filter(date__startswith__lt=timezone.now()).exclude(collectors=None)

    def upcoming(self):
        return self.filter(date__startswith__gt=timezone.now())

    @transaction.atomic
    def process_finished_pickup_dates(self):
        """
        find all pickup dates that are in the past and didn't get processed yet
        add them to history and mark as processed
        """
        for pickup in self.exclude_disabled().filter(
                feedback_possible=False,
                date__startswith__lt=timezone.now(),
        ):
            if not pickup.store.is_active():
                # Make sure we don't process this pickup again, even if the store gets active in future
                pickup.is_disabled = True
                pickup.save()
                continue

            payload = {}
            payload['pickup_date'] = pickup.id
            if pickup.series:
                payload['series'] = pickup.series.id
            if pickup.max_collectors:
                payload['max_collectors'] = pickup.max_collectors
            if pickup.collectors.count() == 0:
                stats.pickup_missed(pickup)
                History.objects.create(
                    typus=HistoryTypus.PICKUP_MISSED,
                    group=pickup.store.group,
                    store=pickup.store,
                    date=pickup.date.start,
                    payload=payload,
                )
            else:
                stats.pickup_done(pickup)
                History.objects.create(
                    typus=HistoryTypus.PICKUP_DONE,
                    group=pickup.store.group,
                    store=pickup.store,
                    users=pickup.collectors.all(),
                    date=pickup.date.start,
                    payload=payload,
                )

            pickup.feedback_possible = True
            pickup.save()


def default_pickup_date_range():
    return CustomDateTimeTZRange(timezone.now(), timezone.now() + timedelta(minutes=30))


def to_range(date, **kwargs):
    if not kwargs:
        kwargs['minutes'] = 30
    return CustomDateTimeTZRange(date, date + timedelta(**kwargs))


class PickupDate(BaseModel, ConversationMixin):
    objects = PickupDateQuerySet.as_manager()

    class Meta:
        ordering = ['date']

    series = models.ForeignKey(
        'PickupDateSeries',
        related_name='pickup_dates',
        on_delete=models.SET_NULL,
        null=True,
    )
    store = models.ForeignKey(
        'stores.Store',
        related_name='pickup_dates',
        on_delete=models.CASCADE,
    )
    collectors = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='pickup_dates',
        through='PickupDateCollector',
        through_fields=('pickupdate', 'user')
    )
    feedback_given_by = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        related_name='feedback_about_pickups',
        through='Feedback',
        through_fields=('about', 'given_by')
    )
    date = CustomDateTimeRangeField(default=default_pickup_date_range)
    description = models.TextField(blank=True)
    max_collectors = models.PositiveIntegerField(null=True)
    is_disabled = models.BooleanField(default=False)
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name='pickups_changed',
        on_delete=models.SET_NULL,
    )

    # Is set to true when the pickup is done
    feedback_possible = models.BooleanField(default=False)

    @property
    def group(self):
        return self.store.group

    @property
    def has_ended(self):
        return not self.is_upcoming()

    def __str__(self):
        return 'PickupDate {} - {}'.format(self.date.start, self.store)

    def feedback_due(self):
        return self.date.end + relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    def is_upcoming(self):
        return self.date.start > timezone.now()

    def is_full(self):
        if not self.max_collectors:
            return False
        return self.collectors.count() >= self.max_collectors

    def is_collector(self, user):
        return self.collectors.filter(id=user.id).exists()

    def is_empty(self):
        return self.collectors.count() == 0

    def is_recent(self):
        return self.date.start >= timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

    def empty_collectors_count(self):
        return max(0, self.max_collectors - self.collectors.count())

    def add_collector(self, user):
        collector, _ = PickupDateCollector.objects.get_or_create(
            pickupdate=self,
            user=user,
        )
        return collector

    def remove_collector(self, user):
        PickupDateCollector.objects.filter(
            pickupdate=self,
            user=user,
        ).delete()


class PickupDateCollector(BaseModel):
    pickupdate = models.ForeignKey(
        PickupDate,
        on_delete=models.CASCADE,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
    )

    class Meta:
        db_table = 'pickups_pickupdate_collectors'
        unique_together = (('pickupdate', 'user'), )
        ordering = ['created_at']


class Feedback(BaseModel):
    given_by = models.ForeignKey('users.User', on_delete=models.CASCADE, related_name='feedback')
    about = models.ForeignKey('PickupDate', on_delete=models.CASCADE)
    weight = models.FloatField(
        blank=True, null=True, validators=[MinValueValidator(-0.01),
                                           MaxValueValidator(10000.0)]
    )
    comment = models.CharField(max_length=settings.DESCRIPTION_MAX_LENGTH, blank=True)

    class Meta:
        unique_together = ('about', 'given_by')
