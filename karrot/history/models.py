from datetime import timedelta

from django.db.models import JSONField
from django.db import models
from django.db.models import IntegerField
from django.db.models.expressions import RawSQL, When, Case
from django.dispatch import Signal
from django.utils import timezone
from django_enumfield import enum

from karrot.base.base_models import NicelyFormattedModel
from karrot.history.utils import without_keys

history_created = Signal()


class HistoryTypus(enum.Enum):
    GROUP_CREATE = 0
    GROUP_MODIFY = 1
    GROUP_JOIN = 2
    GROUP_LEAVE = 3
    STORE_CREATE = 4
    STORE_MODIFY = 5
    STORE_DELETE = 6
    ACTIVITY_CREATE = 7
    ACTIVITY_MODIFY = 8
    ACTIVITY_DELETE = 9
    SERIES_CREATE = 10
    SERIES_MODIFY = 11
    SERIES_DELETE = 12
    ACTIVITY_DONE = 13
    ACTIVITY_JOIN = 14
    ACTIVITY_LEAVE = 15
    ACTIVITY_MISSED = 16
    APPLICATION_DECLINED = 17
    MEMBER_BECAME_EDITOR = 18
    ACTIVITY_DISABLE = 19
    ACTIVITY_ENABLE = 20
    GROUP_LEAVE_INACTIVE = 21
    GROUP_CHANGE_PHOTO = 22
    GROUP_DELETE_PHOTO = 23
    MEMBER_REMOVED = 24
    ACTIVITY_TYPE_CREATE = 25
    ACTIVITY_TYPE_MODIFY = 26
    ACTIVITY_TYPE_DELETE = 27
    USER_LOST_EDITOR_ROLE = 28
    PLACE_TYPE_CREATE = 29
    PLACE_TYPE_MODIFY = 30
    PLACE_TYPE_DELETE = 31


class HistoryQuerySet(models.QuerySet):
    def create(self, typus, group, **kwargs):
        entry = super().create(typus=typus, group=group, **without_keys(kwargs, {'users'}))
        if kwargs.get('users') is not None:
            entry.users.add(*kwargs['users'])

        # TODO remove and just use post_save signal
        history_created.send(sender=History.__class__, instance=entry)
        return entry

    def activity_left_late(self, **kwargs):
        return self.annotate_activity_leave_seconds().filter(
            typus=HistoryTypus.ACTIVITY_LEAVE,
            activity_leave_seconds__lte=timedelta(**kwargs).total_seconds(),
        )

    def annotate_activity_leave_seconds(self):
        sql = f"""
            ROUND (
                EXTRACT (
                    EPOCH FROM (
                        "{History._meta.db_table}"."payload" #>> ARRAY['date','0']
                    ) :: timestamp with time zone
                )
                -
                EXTRACT (EPOCH FROM "{History._meta.db_table}"."date")
            )
        """
        return self.annotate(
            activity_leave_seconds=Case(
                When(
                    typus=HistoryTypus.ACTIVITY_LEAVE,
                    then=RawSQL(sql, [], output_field=IntegerField()),
                ),
                default=None,
            ),
        )


class History(NicelyFormattedModel):
    objects = HistoryQuerySet.as_manager()

    class Meta:
        ordering = ['-date']

    date = models.DateTimeField(default=timezone.now)
    typus = enum.EnumField(HistoryTypus)
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    place = models.ForeignKey('places.Place', null=True, on_delete=models.CASCADE)
    activity = models.ForeignKey('activities.Activity', null=True, on_delete=models.SET_NULL)
    series = models.ForeignKey('activities.ActivitySeries', null=True, on_delete=models.SET_NULL)
    users = models.ManyToManyField('users.User')
    payload = JSONField(null=True)
    before = JSONField(null=True)
    after = JSONField(null=True)
    message = models.TextField(null=True)

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
