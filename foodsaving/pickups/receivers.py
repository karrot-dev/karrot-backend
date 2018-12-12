from django.db.models.signals import pre_delete, post_save, post_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone

from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupMembership
from foodsaving.pickups import stats
from foodsaving.pickups.models import PickupDate, Feedback, PickupDateCollector
from foodsaving.stores.models import Store, StoreStatus


@receiver(pre_delete, sender=GroupMembership)
def leave_group_handler(sender, instance, **kwargs):
    group = instance.group
    user = instance.user
    for _ in PickupDate.objects. \
            filter(date__gte=timezone.now()). \
            filter(collectors__in=[user, ]). \
            filter(store__group=group):
        _.remove_collector(user)


@receiver(post_save, sender=Feedback)
def feedback_created(sender, instance, created, **kwargs):
    if not created:
        return
    stats.feedback_given(instance)


@receiver(post_save, sender=PickupDate)
def pickup_created(**kwargs):
    """Ensure every pickup has a conversation with the collectors in it."""
    pickup = kwargs.get('instance')
    if pickup.id is not None:
        conversation = Conversation.objects.get_or_create_for_target(pickup)
        conversation.sync_users(pickup.collectors.all())


@receiver(pre_delete, sender=PickupDate)
def pickup_deleted(**kwargs):
    """Delete the conversation when the pickup is deleted."""
    pickup = kwargs.get('instance')
    conversation = Conversation.objects.get_for_target(pickup)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=PickupDateCollector)
@receiver(post_delete, sender=PickupDateCollector)
def sync_pickup_collectors_conversation(sender, instance, **kwargs):
    """Update conversation participants when collectors are added or removed."""
    pickup = instance.pickupdate
    conversation = Conversation.objects.get_or_create_for_target(pickup)
    conversation.sync_users(pickup.collectors.all())


@receiver(pre_save, sender=Store)
def update_pickup_series_when_store_changes(sender, instance, **kwargs):
    store = instance

    if not store.id:
        return

    old = Store.objects.get(id=store.id)
    store_became_active = old.status != store.status and store.status == StoreStatus.ACTIVE.value
    weeks_in_advance_changed = old.weeks_in_advance != store.weeks_in_advance
    if store_became_active or weeks_in_advance_changed:
        for series in store.series.all():
            series.update_pickups()
