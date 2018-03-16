from django.db.models.signals import post_save, pre_delete, post_init
from django.dispatch import receiver, Signal

from foodsaving.conversations.models import Conversation
from foodsaving.groups import roles, stats
from foodsaving.groups.models import Group, GroupMembership
from foodsaving.groups.roles import GROUP_APPROVED_MEMBER
from foodsaving.history.models import History, HistoryTypus

roles_changed = Signal(providing_args=['added_roles', 'removed_roles'])


@receiver(post_save, sender=Group)
def group_created(sender, instance, created, **kwargs):
    """Ensure every group has a conversation."""
    if created:
        group = instance
        conversation = Conversation.objects.get_or_create_for_target(group)
        conversation.sync_users(group.members_with_role(GROUP_APPROVED_MEMBER))


@receiver(pre_delete, sender=Group)
def group_deleted(**kwargs):
    """Delete the conversation when the group is deleted."""
    group = kwargs.get('instance')
    conversation = Conversation.objects.get_for_target(group)
    if conversation:
        conversation.delete()


@receiver(post_init, sender=GroupMembership)
def membership_initialized(sender, instance, **kwargs):
    membership = instance
    # we cache the original roles so we can tell when others have been added/removed
    membership._existing_roles = list(membership.roles)


@receiver(post_save, sender=GroupMembership)
def check_membership_role_changes(sender, instance, created, **kwargs):
    membership = instance

    if created:
        added_roles = set(membership.roles)
        removed_roles = set()
    else:
        added_roles = set(membership.roles) - set(membership._existing_roles)
        removed_roles = set(membership._existing_roles) - set(membership.roles)

    if len(added_roles) > 0 or len(removed_roles) > 0:
        roles_changed.send(
            sender=GroupMembership,
            instance=membership,
            added_roles=added_roles,
            removed_roles=removed_roles,
            created=created,
        )

    membership._existing_roles = list(membership.roles)


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    # TODO: only send 'join' stat when group member is approved
    membership = instance
    group = membership.group
    if created:
        stats.group_joined(group)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    membership = instance
    group = membership.group
    user = membership.user
    conversation = Conversation.objects.get_for_target(group)
    if conversation:
        conversation.leave(user)
    stats.group_left(group)
    if roles.GROUP_APPROVED_MEMBER in membership.roles:
        History.objects.create(
            typus=HistoryTypus.GROUP_LEAVE,
            group=group,
            users=[user, ]
        )


@receiver(roles_changed, sender=GroupMembership)
def group_membership_roles_changed(sender, instance, added_roles, removed_roles, created, **kwargs):
    membership = instance
    group = membership.group
    user = membership.user

    conversation = Conversation.objects.get_or_create_for_target(group)
    if roles.GROUP_APPROVED_MEMBER in added_roles:
        conversation.join(user)
        if not created:
            # the creation case is handled in add_member, to be able to write history context
            History.objects.create(
                typus=HistoryTypus.GROUP_JOIN,
                group=group,
                users=[user, ],
            )
    elif roles.GROUP_APPROVED_MEMBER in removed_roles:
        conversation.leave(user)


@receiver(post_init, sender=Group)
@receiver(post_save, sender=GroupMembership)
def initialize_group(sender, instance, **kwargs):
    """
    Configure membership roles for the group.

    This implements a default model of group roles so that there is always someone who can manage the
    roles and edit the agreement.
    """

    if sender is Group:
        group = instance
    elif sender is GroupMembership:
        group = instance.group

    memberships = GroupMembership.objects.filter(group=group)
    if not memberships.filter(roles__contains=[roles.GROUP_MEMBERSHIP_MANAGER]).exists():
        oldest = memberships.order_by('created_at', 'id').first()
        if oldest:
            oldest.roles.append(roles.GROUP_MEMBERSHIP_MANAGER)
            oldest.save()
            if oldest.id is instance.id:
                # our instance has changed, so refresh it!
                instance.refresh_from_db()
                membership_initialized(sender=GroupMembership, instance=instance)
