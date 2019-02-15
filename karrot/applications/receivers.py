from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from karrot.applications.tasks import notify_members_about_new_application
from karrot.conversations.models import Conversation
from karrot.groups.models import GroupMembership, GroupNotificationType
from karrot.applications.models import Application, ApplicationStatus
from karrot.users.models import post_erase_user


@receiver(post_save, sender=Application)
def application_saved(sender, instance, created, **kwargs):
    if created:
        application = instance
        group = instance.group
        applicant = instance.user

        conversation = Conversation.objects.get_or_create_for_target(application)
        conversation.join(applicant)
        for membership in group.groupmembership_set.all():
            muted = GroupNotificationType.NEW_APPLICATION not in membership.notification_types
            conversation.join(membership.user, muted=muted)

        notify_members_about_new_application(application)


@receiver(pre_delete, sender=Application)
def delete_application_conversation(sender, instance, **kwargs):
    application = instance

    conversation = Conversation.objects.get_for_target(application)
    conversation.delete()


@receiver(post_save, sender=GroupMembership)
def group_member_added(sender, instance, created, **kwargs):
    if created:
        group = instance.group
        user = instance.user

        for application in group.application_set.all():
            conversation = Conversation.objects.get_for_target(application)
            conversation.join(user)


@receiver(pre_delete, sender=GroupMembership)
def group_member_removed(sender, instance, **kwargs):
    group = instance.group
    user = instance.user

    for application in group.application_set.all():
        conversation = Conversation.objects.get_for_target(application)
        if conversation:
            conversation.leave(user)


@receiver(post_erase_user)
def user_erased(sender, instance, **kwargs):
    user = instance
    for application in user.application_set.filter(status=ApplicationStatus.PENDING.value):
        application.withdraw()
