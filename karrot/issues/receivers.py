from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from karrot.conversations.models import Conversation
from karrot.groups.models import GroupNotificationType, GroupMembership
from karrot.issues.models import Issue, Voting
from karrot.issues.tasks import notify_about_new_conflict_resolution, \
    notify_about_continued_conflict_resolution


@receiver(post_save, sender=Issue)
def issue_created(sender, instance, created, **kwargs):
    if not created:
        return

    issue = instance
    group = instance.group

    # add conversation
    conversation = Conversation.objects.get_or_create_for_target(issue)
    for membership in group.groupmembership_set.all():
        notifications_enabled = GroupNotificationType.CONFLICT_RESOLUTION in membership.notification_types
        if notifications_enabled:
            conversation.join(membership.user, muted=False)

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

    for issue in group.issues.all():
        conversation = Conversation.objects.get_for_target(issue)
        if conversation:
            conversation.leave(user)

    # if user was affected by ongoing issue, cancel that issue
    for issue in group.issues.ongoing().filter(affected_user=user):
        issue.cancel()
