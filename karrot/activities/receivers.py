from datetime import timedelta

from django.conf import settings
from django.db.models.signals import post_delete, post_save, pre_delete, pre_save
from django.dispatch import receiver
from django.utils import timezone
from huey.contrib.djhuey import revoke_by_id

from karrot.activities import stats, tasks
from karrot.activities.models import (
    Activity,
    ActivityParticipant,
    ActivitySeries,
    Feedback,
    create_activity_banner_image_warmer,
)
from karrot.conversations.models import Conversation
from karrot.groups.models import GroupMembership
from karrot.places.models import Place


@receiver(pre_delete, sender=GroupMembership)
def leave_group_handler(sender, instance, **kwargs):
    group = instance.group
    user = instance.user
    for activity in (
        Activity.objects.filter(date__startswith__gte=timezone.now())
        .filter(
            participants__in=[
                user,
            ]
        )
        .filter(place__group=group)
    ):
        activity.remove_participant(user)


@receiver(post_save, sender=Feedback)
def feedback_created(sender, instance, created, **kwargs):
    if not created:
        return
    stats.feedback_given(instance)


@receiver(post_save, sender=Activity)
def activity_created(sender, instance, created, **kwargs):
    """Ensure every activity has a conversation with the participants in it."""
    activity = instance
    if not created:
        return
    conversation = Conversation.objects.get_or_create_for_target(activity)
    conversation.sync_users(activity.participants.all())


@receiver(pre_delete, sender=Activity)
def activity_deleted(sender, instance, **kwargs):
    """Delete the conversation when the activity is deleted."""
    activity = instance
    conversation = Conversation.objects.get_for_target(activity)
    if conversation:
        conversation.delete()


@receiver(post_save, sender=ActivityParticipant)
def add_activity_participant_to_conversation(sender, instance, **kwargs):
    """Add participant to conversation when added."""
    user = instance.user
    activity = instance.activity
    conversation = Conversation.objects.get_or_create_for_target(activity)
    conversation.join(user)


@receiver(post_delete, sender=ActivityParticipant)
def remove_activity_participant_from_conversation(sender, instance, **kwargs):
    """Remove participant from conversation when removed."""
    user = instance.user
    activity = instance.activity
    conversation = Conversation.objects.get_or_create_for_target(activity)
    conversation.leave(user)


@receiver(post_save, sender=ActivityParticipant)
def schedule_activity_reminder(sender, instance, **kwargs):
    participant = instance
    if participant.reminder_task_id:
        return

    activity = participant.activity
    remind_at = activity.date.start - timedelta(hours=settings.ACTIVITY_REMINDER_HOURS)
    if remind_at > timezone.now():
        task = tasks.activity_reminder.schedule(
            (participant.id,),
            eta=remind_at,
        )
        participant.reminder_task_id = task.id
        participant.save()


@receiver(post_delete, sender=ActivityParticipant)
def revoke_activity_reminder(sender, instance, **kwargs):
    participant = instance
    if participant.reminder_task_id:
        revoke_by_id(participant.reminder_task_id)


@receiver(pre_save, sender=Place)
def update_activity_series_when_place_changes(sender, instance, **kwargs):
    place = instance

    if not place.id:
        return

    old = Place.objects.get(id=place.id)
    place_became_unarchived = old.archived_at is not None and place.archived_at is None
    weeks_in_advance_changed = old.weeks_in_advance != place.weeks_in_advance
    if place_became_unarchived or weeks_in_advance_changed:
        for series in place.series.all():
            series.update_activities()


@receiver(post_save, sender=Activity)
def warm_activity_banner_image(sender, instance, **kwargs):
    if instance.banner_image:
        create_activity_banner_image_warmer(instance).warm()


@receiver(post_save, sender=ActivitySeries)
def warm_activity_series_banner_image(sender, instance, **kwargs):
    if instance.banner_image:
        create_activity_banner_image_warmer(instance).warm()
