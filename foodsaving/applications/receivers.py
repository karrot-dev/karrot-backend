from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from foodsaving.applications.tasks import notify_members_about_new_application
from foodsaving.conversations.models import Conversation
from foodsaving.groups.models import GroupMembership, GroupNotificationType
from foodsaving.applications.models import GroupApplication


@receiver(post_save, sender=GroupApplication)
def group_application_saved(sender, instance, created, **kwargs):
    if created:
        application = instance
        group = instance.group
        applicant = instance.user

        conversation = Conversation.objects.get_or_create_for_target(application)
        conversation.join(applicant)
        for membership in group.groupmembership_set.all():
            notifications_enabled = GroupNotificationType.NEW_APPLICATION in membership.notification_types
            conversation.join(membership.user, email_notifications=notifications_enabled)

        notify_members_about_new_application(application)


@receiver(pre_delete, sender=GroupApplication)
def delete_group_application_conversation(sender, instance, **kwargs):
    application = instance

    conversation = Conversation.objects.get_for_target(application)
    conversation.delete()


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    if created:
        group = instance.group
        user = instance.user

        for application in group.groupapplication_set.all():
            conversation = Conversation.objects.get_for_target(application)
            conversation.join(user)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    group = instance.group
    user = instance.user

    for application in group.groupapplication_set.all():
        conversation = Conversation.objects.get_for_target(application)
        if conversation:
            conversation.leave(user)
