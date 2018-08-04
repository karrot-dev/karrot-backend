from django.db.models.signals import post_save, pre_delete, post_delete
from django.dispatch import receiver

from foodsaving.conversations.models import Conversation
from foodsaving.groups import roles, stats
from foodsaving.groups.emails import prepare_user_became_editor_email
from foodsaving.groups.models import Group, GroupMembership, Trust, GroupNotificationType


@receiver(post_save, sender=Group)
def group_created(sender, instance, created, **kwargs):
    """Ensure every group has a conversation."""
    if not created:
        return
    group = instance
    conversation = Conversation.objects.get_or_create_for_target(group)
    conversation.sync_users(group.members.all())


@receiver(pre_delete, sender=Group)
def group_deleted(sender, instance, **kwargs):
    """Delete the conversation when the group is deleted."""
    group = instance
    conversation = Conversation.objects.get_for_target(group)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    if not created:
        return
    group = instance.group
    user = instance.user
    membership = instance
    if group.is_playground():
        membership.notification_types = []
        membership.save()

    conversation = Conversation.objects.get_or_create_for_target(group)
    conversation.join(user, email_notifications=not group.is_playground())

    stats.group_joined(group)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    """When a user is removed from a conversation we will notify them."""
    group = instance.group
    user = instance.user
    conversation = Conversation.objects.get_for_target(group)
    if conversation:
        conversation.leave(user)

    stats.group_left(group)


@receiver(post_save, sender=GroupMembership)
@receiver(post_delete, sender=GroupMembership)
def initialize_group(sender, instance, **kwargs):
    """
    Configure membership roles for the group.

    This implements a default model of group roles so that there is always someone who can manage the
    roles and edit the agreement.
    """
    group = instance.group

    memberships = GroupMembership.objects.filter(group=group)
    if not memberships.filter(roles__contains=[roles.GROUP_MEMBERSHIP_MANAGER]).exists():
        oldest = memberships.order_by('created_at', 'id').first()
        if oldest:
            oldest.roles.append(roles.GROUP_MEMBERSHIP_MANAGER)
            oldest.save()


@receiver(post_save, sender=Trust)
def trust_given(sender, instance, created, **kwargs):
    if not created:
        return

    membership = instance.membership
    relevant_trust = Trust.objects.filter(membership=membership)
    trust_threshold = membership.group.get_trust_threshold_for_newcomer()

    if relevant_trust.count() >= trust_threshold:
        membership.add_roles([roles.GROUP_EDITOR])

        # new editors should also get informed about new applications
        membership.add_notification_types([GroupNotificationType.NEW_APPLICATION])
        membership.save()
        prepare_user_became_editor_email(user=membership.user, group=membership.group).send()

    stats.trust_given(membership.group)


@receiver(pre_delete, sender=GroupMembership)
def remove_trust(sender, instance, **kwargs):
    membership = instance

    Trust.objects.filter(given_by=membership.user).delete()
