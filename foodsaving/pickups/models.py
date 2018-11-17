import dateutil.rrule
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models
from django.db import transaction
from django.db.models import Count, Q
from django.dispatch import Signal
from django.utils import timezone

from foodsaving.base.base_models import BaseModel
from foodsaving.conversations.models import ConversationMixin
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups import stats
from foodsaving.pickups.utils import match_pickups_with_dates, rrule_between_dates_in_local_time
from foodsaving.stores.models import StoreStatus

pickup_done = Signal()


class PickupDateSeriesQuerySet(models.QuerySet):
    @transaction.atomic
    def create_all_pickup_dates(self):
        for series in self.filter(store__status=StoreStatus.ACTIVE.value):
            series.update_pickup_dates()


class PickupDateSeries(BaseModel):
    objects = PickupDateSeriesQuerySet.as_manager()

    store = models.ForeignKey('stores.Store', related_name='series', on_delete=models.CASCADE)
    max_collectors = models.PositiveIntegerField(blank=True, null=True)
    rule = models.TextField()
    start_date = models.DateTimeField()
    description = models.TextField(blank=True)

    @transaction.atomic
    def delete(self, *args, **kwargs):
        for pickup in self.pickup_dates.\
                filter(date__gte=timezone.now()).\
                annotate(Count('collectors')).\
                filter(collectors__count=0):
            pickup.deleted = True
            pickup.save()
        return super().delete(*args, **kwargs)

    def get_dates_for_rule(self, period_start):
        return rrule_between_dates_in_local_time(
            rule=self.rule,
            dtstart=self.start_date,
            tz=self.store.group.timezone,
            period_start=period_start,
            period_duration=relativedelta(weeks=self.store.weeks_in_advance)
        )

    def update_pickup_dates(self, start=timezone.now):
        """
        synchronizes pickup dates with series

        changes to series fields are also made to pickup dates, except
        - the field on the pickup date has been modified
        - users have joined the pickup date
        """

        # shift start time slightly into future to avoid pickup dates which are only valid for very short time
        period_start = start() + relativedelta(minutes=5)

        for pickup, new_date in match_pickups_with_dates(
                pickups=self.pickup_dates.order_by('date').filter(date__gte=period_start),
                new_dates=self.get_dates_for_rule(period_start=period_start),
        ):
            if not pickup:
                # does not yet exist
                PickupDate.objects.create(
                    date=new_date,
                    max_collectors=self.max_collectors,
                    series=self,
                    store=self.store,
                    description=self.description
                )
            elif pickup.collectors.count() < 1:
                # only modify pickups when nobody has joined
                if not new_date:
                    # series changed and now this pickup should not exist anymore
                    pickup.delete()
                else:
                    if not pickup.is_date_changed:
                        pickup.date = new_date
                    if not pickup.is_max_collectors_changed:
                        pickup.max_collectors = self.max_collectors
                    if not pickup.is_description_changed:
                        pickup.description = self.description
                    pickup.save()

    def __str__(self):
        return 'PickupDateSeries {} - {}'.format(self.rule, self.store)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.update_pickup_dates()


class PickupDateQuerySet(models.QuerySet):
    def _feedback_possible_q(self, user):
        return Q(done_and_processed=True) \
               & Q(date__gte=timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)) \
               & Q(collectors=user) \
               & ~Q(feedback__given_by=user)

    def only_feedback_possible(self, user):
        return self.filter(self._feedback_possible_q(user))

    def exclude_feedback_possible(self, user):
        return self.filter(~self._feedback_possible_q(user))

    def annotate_num_collectors(self):
        return self.annotate(num_collectors=Count('collectors'))

    def exclude_deleted(self):
        return self.filter(deleted=False)

    def in_group(self, group):
        return self.filter(store__group=group)

    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.PICKUPDATE_DUE_SOON_HOURS)
        return self.exclude_deleted().filter(date__gt=timezone.now(), date__lt=in_some_hours)

    def missed(self):
        return self.exclude_deleted().filter(date__lt=timezone.now(), collectors=None)

    def done(self):
        return self.exclude_deleted().filter(date__lt=timezone.now()).exclude(collectors=None)

    @transaction.atomic
    def process_finished_pickup_dates(self):
        """find all pickup dates that are in the past and didn't get processed yet and add them to history
        """
        for pickup in self.filter(
                done_and_processed=False,
                date__lt=timezone.now(),
        ).exclude_deleted():
            if pickup.store.is_active():
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
                        date=pickup.date,
                        payload=payload,
                    )
                else:
                    stats.pickup_done(pickup)
                    History.objects.create(
                        typus=HistoryTypus.PICKUP_DONE,
                        group=pickup.store.group,
                        store=pickup.store,
                        users=pickup.collectors.all(),
                        date=pickup.date,
                        payload=payload,
                    )

            pickup.done_and_processed = True
            pickup.save()

            pickup_done.send(sender=PickupDate.__class__, instance=pickup)


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
    date = models.DateTimeField()
    description = models.TextField(blank=True)
    max_collectors = models.PositiveIntegerField(null=True)
    deleted = models.BooleanField(default=False)

    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        related_name='pickups_cancelled',
        on_delete=models.SET_NULL,
    )
    cancelled_at = models.DateTimeField(null=True)

    # internal values for change detection
    # used when the respective value in the series gets updated
    is_date_changed = models.BooleanField(default=False)
    is_max_collectors_changed = models.BooleanField(default=False)
    is_description_changed = models.BooleanField(default=False)

    # internal value to find out if this has been processed
    # e.g. logged to history as PICKUP_DONE or PICKUP_MISSED
    done_and_processed = models.BooleanField(default=False)

    @property
    def group(self):
        return self.store.group

    def __str__(self):
        return 'PickupDate {} - {}'.format(self.date, self.store)

    def is_upcoming(self):
        return self.date > timezone.now()

    def is_full(self):
        if not self.max_collectors:
            return False
        return self.collectors.count() >= self.max_collectors

    def is_collector(self, user):
        return self.collectors.filter(id=user.id).exists()

    def is_empty(self):
        return self.collectors.count() == 0

    def is_recent(self):
        return self.date >= timezone.now() - relativedelta(days=settings.FEEDBACK_POSSIBLE_DAYS)

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

    def cancel(self, user):
        self.cancelled_at = timezone.now()
        self.cancelled_by = user
        self.save()


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
