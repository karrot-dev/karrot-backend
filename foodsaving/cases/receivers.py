from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.cases.models import Case
from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupNotificationType, GroupMembership


@receiver(post_save, sender=Case)
def case_created(sender, instance, created, **kwargs):
    if not created:
        return

    case = instance
    group = instance.group

    conversation = Conversation.objects.get_or_create_for_target(case)
    for membership in group.groupmembership_set.all():
        notifications_enabled = GroupNotificationType.NEW_CASE in membership.notification_types
        conversation.join(membership.user, email_notifications=notifications_enabled)

    # notify_members_about_new_case(case)


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    if not created:
        return

    membership = instance
    group = membership.group
    user = membership.user

    notifications_enabled = GroupNotificationType.NEW_CASE in membership.notification_types
    for case in group.cases.all():
        conversation = Conversation.objects.get_for_target(case)
        conversation.join(user, email_notifications=notifications_enabled)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    group = instance.group
    user = instance.user

    for case in group.cases.all():
        conversation = Conversation.objects.get_for_target(case)
        if conversation:
            conversation.leave(user)
