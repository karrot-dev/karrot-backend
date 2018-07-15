from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver, Signal

from foodsaving.applications.tasks import notify_members_about_new_application
from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupMembership, GroupNotificationType
from foodsaving.applications.models import GroupApplication

post_group_application_save = Signal()


@receiver(post_save, sender=GroupApplication)
def group_application_saved(sender, instance, created, **kwargs):
    if created:
        application = instance
        group = instance.group
        applicant = instance.user

        conversation = Conversation.objects.get_or_create_for_target(application)
        conversation.join(applicant)
        for user in group.members.all():
            membership = GroupMembership.objects.get(user=user, group=group)
            notifications_enabled = GroupNotificationType.NEW_APPLICATION in membership.notification_types
            conversation.join(user, email_notifications=notifications_enabled)

        notify_members_about_new_application(application)

    post_group_application_save.send(
        sender=GroupApplication.__class__,
        instance=instance,
        created=created,
    )


@receiver(pre_delete, sender=GroupApplication)
def delete_group_application_conversation(sender, instance, **kwargs):
    application = instance

    conversation = Conversation.objects.get_for_target(application)
    conversation.delete()
