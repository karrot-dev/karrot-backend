from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from karrot.conversations.models import Conversation
from karrot.groups.models import GroupMembership
from karrot.places.models import Place, PlaceSubscription


@receiver(post_save, sender=Place)
def place_created(sender, instance, created, **kwargs):
    """Ensure every place has a conversation."""
    if not created:
        return
    place = instance
    conversation = Conversation.objects.get_or_create_for_target(place)
    conversation.sync_users(place.subscribers.all())


@receiver(pre_delete, sender=Place)
def place_deleted(sender, instance, **kwargs):
    """Delete the conversation when the place is deleted."""
    place = instance
    conversation = Conversation.objects.get_for_target(place)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=PlaceSubscription)
def subscription_created(sender, instance, created, **kwargs):
    if not created:
        return
    subscription = instance

    conversation = Conversation.objects.get_or_create_for_target(subscription.place)
    conversation.join(subscription.user)


@receiver(pre_delete, sender=PlaceSubscription)
def subscription_removed(sender, instance, **kwargs):
    subscription = instance

    conversation = Conversation.objects.get_for_target(subscription.place)
    if conversation:
        conversation.leave(subscription.user)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    membership = instance

    for subscription in PlaceSubscription.objects.filter(place__group=membership.group, user=membership.user):
        subscription.delete()
