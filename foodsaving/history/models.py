from django.contrib.postgres.fields import JSONField
from django.db import models
from django.dispatch import Signal
from django.utils import timezone
from django_enumfield import enum

from foodsaving.base.base_models import NicelyFormattedModel
from foodsaving.history.utils import without_keys

history_created = Signal()


class HistoryTypus(enum.Enum):
    GROUP_CREATE = 0
    GROUP_MODIFY = 1
    GROUP_JOIN = 2
    GROUP_LEAVE = 3
    STORE_CREATE = 4
    STORE_MODIFY = 5
    STORE_DELETE = 6
    PICKUP_CREATE = 7
    PICKUP_MODIFY = 8
    PICKUP_DELETE = 9
    SERIES_CREATE = 10
    SERIES_MODIFY = 11
    SERIES_DELETE = 12
    PICKUP_DONE = 13
    PICKUP_JOIN = 14
    PICKUP_LEAVE = 15
    PICKUP_MISSED = 16
    GROUP_APPLICATION_DECLINED = 17
    MEMBER_BECAME_EDITOR = 18
    PICKUP_DISABLE = 19
    PICKUP_ENABLE = 20
    GROUP_LEAVE_INACTIVE = 21
    MEMBER_REMOVED = 22


class HistoryQuerySet(models.QuerySet):
    def create(self, typus, group, **kwargs):
        entry = super().create(typus=typus, group=group, **without_keys(kwargs, {'users'}))
        if kwargs.get('users') is not None:
            entry.users.add(*kwargs['users'])

        # TODO remove and just use post_save signal
        history_created.send(sender=History.__class__, instance=entry)
        return entry


class History(NicelyFormattedModel):
    objects = HistoryQuerySet.as_manager()

    class Meta:
        ordering = ['-date']

    date = models.DateTimeField(default=timezone.now)
    typus = enum.EnumField(HistoryTypus)
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    store = models.ForeignKey('stores.Store', null=True, on_delete=models.CASCADE)
    pickup = models.ForeignKey('pickups.PickupDate', null=True, on_delete=models.SET_NULL)
    series = models.ForeignKey('pickups.PickupDateSeries', null=True, on_delete=models.SET_NULL)
    users = models.ManyToManyField('users.User')
    payload = JSONField(null=True)
    before = JSONField(null=True)
    after = JSONField(null=True)

    def __str__(self):
        return 'History {} - {} ({})'.format(self.date, HistoryTypus.name(self.typus), self.group)

    def changed(self):
        before = self.before or {}
        after = self.after or {}
        keys = set(after.keys()).union(before.keys())
        changed_keys = [k for k in keys if before.get(k) != after.get(k)]

        return {
            'before': {k: before.get(k)
                       for k in changed_keys if k in before},
            'after': {k: after.get(k)
                      for k in changed_keys if k in after},
        }
