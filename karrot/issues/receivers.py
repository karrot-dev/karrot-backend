from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from karrot.conversations.models import Conversation
from karrot.groups.models import GroupMembership
from karrot.issues.models import Issue, Vote, Voting
from karrot.issues.tasks import notify_about_continued_conflict_resolution, notify_about_new_conflict_resolution


@receiver(post_save, sender=Issue)
def issue_created(sender, instance, created, **kwargs):
    if not created:
        return

    issue = instance

    # add conversation
    conversation = Conversation.objects.get_or_create_for_target(issue)

    # initially we only add the two people involved, the initiator, and the affected user
    conversation.join(issue.created_by, muted=False)
    conversation.join(issue.affected_user, muted=False)


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

    # remove the users votes for ongoing votings in this group
    Vote.objects.filter(
        user=user,
        option__voting__in=Voting.objects.filter(
            expires_at__gte=timezone.now(),
            accepted_option__isnull=True,
            issue__in=group.issues.ongoing(),
        ),
    ).delete()
