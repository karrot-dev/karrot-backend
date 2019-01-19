from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.cases.models import GroupCase, Voting, CaseParticipant
from foodsaving.cases.tasks import notify_about_new_conflict_resolution_case, \
    notify_about_continued_conflict_resolution_case
from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupNotificationType, GroupMembership


@receiver(post_save, sender=GroupCase)
def case_created(sender, instance, created, **kwargs):
    if not created:
        return

    case = instance
    group = instance.group

    for membership in group.groupmembership_set.editors():
        case.caseparticipant_set.create(user=membership.user)
    case.caseparticipant_set.get_or_create(user=case.affected_user)

    # add conversation
    conversation = Conversation.objects.get_or_create_for_target(case)
    for membership in group.groupmembership_set.editors():
        notifications_enabled = GroupNotificationType.CONFLICT_RESOLUTION in membership.notification_types
        conversation.join(membership.user, email_notifications=notifications_enabled)

    # make sure affected user is in conversation and has email notifications enabled
    conversation.join(case.affected_user)
    participant = conversation.conversationparticipant_set.get(user=case.affected_user)
    participant.email_notifications = True
    participant.save()


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


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    group = instance.group
    user = instance.user

    for participant in CaseParticipant.objects.filter(user=user, case__group=group):
        participant.delete()

    for case in group.cases.all():
        conversation = Conversation.objects.get_for_target(case)
        if conversation:
            conversation.leave(user)

    # if user was affected by ongoing case, cancel that case
    for case in group.cases.ongoing().filter(affected_user=user):
        case.cancel()
