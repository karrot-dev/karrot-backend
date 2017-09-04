from django.dispatch import receiver

from foodsaving.activity.models import Activity, ActivityTypus
from foodsaving.groups.signals import post_group_join, pre_group_leave, post_group_modify, post_group_create
from foodsaving.stores.api import post_store_delete, pre_pickup_delete, pre_series_delete
from foodsaving.stores.signals import post_pickup_create, post_pickup_modify, post_pickup_join, post_pickup_leave, \
    post_series_create, post_series_modify, post_store_create, post_store_modify, pickup_done, pickup_missed


def make_handler(typus):
    def fn(sender, **kwargs):
        a = Activity.objects.create(
            typus=typus,
            group=kwargs.get('group'),
            store=kwargs.get('store'),
            payload=kwargs.get('payload')
        )
        a.users.add(kwargs.get('user'))
        a.save()
    return fn


for signal, typus in [
    (post_group_create, ActivityTypus.GROUP_CREATE),
    (post_group_modify, ActivityTypus.GROUP_MODIFY),
    (post_group_join, ActivityTypus.GROUP_JOIN),
    (pre_group_leave, ActivityTypus.GROUP_LEAVE),
    (post_store_create, ActivityTypus.STORE_CREATE),
    (post_store_modify, ActivityTypus.STORE_MODIFY),
    (post_store_delete, ActivityTypus.STORE_DELETE),
    (post_pickup_create, ActivityTypus.PICKUP_CREATE),
    (post_pickup_modify, ActivityTypus.PICKUP_MODIFY),
    (pre_pickup_delete, ActivityTypus.PICKUP_DELETE),
    (post_series_create, ActivityTypus.SERIES_CREATE),
    (post_series_modify, ActivityTypus.SERIES_MODIFY),
    (pre_series_delete, ActivityTypus.SERIES_DELETE),
    (post_pickup_join, ActivityTypus.PICKUP_JOIN),
    (post_pickup_leave, ActivityTypus.PICKUP_LEAVE),
]:
    signal.connect(make_handler(typus=typus), weak=False)


@receiver(pickup_done)
def handle_pickups_done(sender, **kwargs):
    a = Activity.objects.create(
        typus=ActivityTypus.PICKUP_DONE,
        date=kwargs.get('date'),
        group=kwargs.get('group'),
        store=kwargs.get('store'),
        payload=kwargs.get('payload'),
    )
    a.users.set(kwargs.get('users'))
    a.save()


@receiver(pickup_missed)
def handle_pickups_missed(sender, **kwargs):
    a = Activity.objects.create(
        typus=ActivityTypus.PICKUP_MISSED,
        date=kwargs.get('date'),
        group=kwargs.get('group'),
        store=kwargs.get('store'),
        payload=kwargs.get('payload'),
    )
    a.save()
