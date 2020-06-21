from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from karrot.issues.models import Issue, Voting, IssueParticipant
from karrot.issues.tasks import (
    notify_about_new_conflict_resolution,
    notify_about_continued_conflict_resolution,
)
from karrot.conversations.models import Conversation
from karrot.groups.models import GroupNotificationType, GroupMembership


@receiver(post_save, sender=Issue)
def issue_created(sender, instance, created, **kwargs):
    if not created:
        return

    issue = instance
    group = instance.group

    for membership in group.groupmembership_set.editors():
        issue.issueparticipant_set.create(user=membership.user)
    issue.issueparticipant_set.get_or_create(user=issue.affected_user)

    # add conversation
    conversation = Conversation.objects.get_or_create_for_target(issue)
    for membership in group.groupmembership_set.editors():
        notifications_enabled = (
            GroupNotificationType.CONFLICT_RESOLUTION in membership.notification_types
        )
        conversation.join(membership.user, muted=not notifications_enabled)

    # make sure affected user is in conversation and has email notifications enabled
    conversation.join(issue.affected_user)
    participant = conversation.conversationparticipant_set.get(user=issue.affected_user)
    participant.muted = False
    participant.save()


@receiver(post_save, sender=Voting)
def voting_created(sender, instance, created, **kwargs):
    if not created:
        return

    voting = instance
    issue = voting.issue

    voting_count = issue.votings.count()
    if voting_count == 1:
        notify_about_new_conflict_resolution(issue)
    elif voting_count > 1:
        notify_about_continued_conflict_resolution(issue)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    group = instance.group
    user = instance.user

    for participant in IssueParticipant.objects.filter(user=user, issue__group=group):
        participant.delete()

    for issue in group.issues.all():
        conversation = Conversation.objects.get_for_target(issue)
        if conversation:
            conversation.leave(user)

    # if user was affected by ongoing issue, cancel that issue
    for issue in group.issues.ongoing().filter(affected_user=user):
        issue.cancel()
