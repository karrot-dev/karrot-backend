from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupMembership
from foodsaving.stores.models import Store


@receiver(post_save, sender=Store)
def store_created(sender, instance, created, **kwargs):
    """Ensure every store has a conversation."""
    if not created:
        return
    store = instance
    conversation = Conversation.objects.get_or_create_for_target(store)
    conversation.sync_users(store.group.members.all())


@receiver(pre_delete, sender=Store)
def store_deleted(sender, instance, **kwargs):
    """Delete the conversation when the store is deleted."""
    store = instance
    conversation = Conversation.objects.get_for_target(store)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    if not created:
        return
    group = instance.group
    user = instance.user

    for store in group.stores.all():
        conversation = Conversation.objects.get_or_create_for_target(store)
        conversation.join(user)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    """When a user is removed from a conversation we will notify them."""
    group = instance.group
    user = instance.user

    for store in group.stores.all():
        conversation = Conversation.objects.get_for_target(store)
        if conversation:
            conversation.leave(user)
