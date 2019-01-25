from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupMembership
from foodsaving.stores.models import Store, StoreSubscription


@receiver(post_save, sender=Store)
def store_created(sender, instance, created, **kwargs):
    """Ensure every store has a conversation."""
    if not created:
        return
    store = instance
    conversation = Conversation.objects.get_or_create_for_target(store)
    conversation.sync_users(store.subscribers.all())


@receiver(pre_delete, sender=Store)
def store_deleted(sender, instance, **kwargs):
    """Delete the conversation when the store is deleted."""
    store = instance
    conversation = Conversation.objects.get_for_target(store)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=StoreSubscription)
def subscription_created(sender, instance, created, **kwargs):
    if not created:
        return
    subscription = instance

    conversation = Conversation.objects.get_or_create_for_target(subscription.store)
    conversation.join(subscription.user)


@receiver(pre_delete, sender=StoreSubscription)
def subscription_removed(sender, instance, **kwargs):
    subscription = instance

    conversation = Conversation.objects.get_for_target(subscription.store)
    if conversation:
        conversation.leave(subscription.user)
