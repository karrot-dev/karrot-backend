from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch import receiver

from foodsaving.cases.models import Case, Voting
from foodsaving.cases.tasks import notify_about_new_conflict_resolution_case, \
    notify_about_continued_conflict_resolution_case
from foodsaving.conversations.models import Conversation
from foodsaving.groups import roles
from foodsaving.groups.models import GroupNotificationType, GroupMembership


@receiver(post_save, sender=Case)
def case_created(sender, instance, created, **kwargs):
    if not created:
        return

    case = instance
    group = instance.group

    conversation = Conversation.objects.get_or_create_for_target(case)
    for membership in group.groupmembership_set.editors():
        notifications_enabled = GroupNotificationType.CONFLICT_RESOLUTION in membership.notification_types
        conversation.join(membership.user, email_notifications=notifications_enabled)

    # make sure affected user is in conversation and has email notifications enabled
    conversation.join(case.affected_user)
    conversation.conversationparticipant_set.filter(user=case.affected_user).update(email_notifications=True)


@receiver(post_save, sender=Voting)
def voting_created(sender, instance, created, **kwargs):
    if not created:
        return

    voting = instance
    case = voting.case

    voting_count = case.votings.count()
    if voting_count == 1:
        notify_about_new_conflict_resolution_case(case)
    elif voting_count > 1:
        notify_about_continued_conflict_resolution_case(case)


@receiver(pre_save, sender=GroupMembership)
def add_participant_if_user_became_editor(sender, instance, **kwargs):
    membership = instance
    group = membership.group
    user = membership.user

    if roles.GROUP_EDITOR not in membership.roles:
        return

    if membership.id:
        old = GroupMembership.objects.get(id=membership.id)

        if roles.GROUP_EDITOR in old.roles:
            # member was already editor
            return

    notifications_enabled = GroupNotificationType.CONFLICT_RESOLUTION in membership.notification_types
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
