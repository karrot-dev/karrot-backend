from django.contrib.postgres.fields.jsonb import KeyTextTransform
from django.db.models import IntegerField
from django.db.models.functions import Cast
from huey import crontab
from huey.contrib.djhuey import db_periodic_task

from foodsaving.notifications.models import Notification, NotificationType
from foodsaving.pickups.models import PickupDate, PickupDateCollector


@db_periodic_task(crontab(minute='*'))  # every minute
def delete_expired_notifications():
    Notification.objects.expired().delete()


@db_periodic_task(crontab(minute='*'))  # every minute
def create_pickup_upcoming_notifications():
    # Oh oh, this is a bit complex. As notification.context is a JSONField, the collectors_already_notified subquery
    # would return a jsonb object by default (which can't be compared to integer).
    # We can work around this by transforming the property value to text ("->>" lookup) and then casting to integer
    collectors_already_notified = Notification.objects.\
        order_by().\
        filter(type=NotificationType.PICKUP_UPCOMING.value).\
        exclude(context__pickup_collector=None).\
        values_list(Cast(KeyTextTransform('pickup_collector', 'context'), IntegerField()), flat=True)
    pickups_due_soon = PickupDate.objects.order_by().due_soon()
    collectors = PickupDateCollector.objects.\
        filter(pickupdate__in=pickups_due_soon).\
        exclude(id__in=collectors_already_notified).\
        distinct()

    for collector in collectors:
        Notification.objects.create(
            type=NotificationType.PICKUP_UPCOMING.value,
            user=collector.user,
            expires_at=collector.pickupdate.date,
            context={
                'group': collector.pickupdate.place.group.id,
                'place': collector.pickupdate.place.id,
                'pickup': collector.pickupdate.id,
                'pickup_collector': collector.id,
            },
        )
