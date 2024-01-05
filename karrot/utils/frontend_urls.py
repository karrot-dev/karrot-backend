import re

from django.conf import settings
from furl import furl

from karrot.groups.models import GroupNotificationType
from karrot.unsubscribe.utils import generate_token


def message_url(message):
    if message.is_thread_reply():
        return thread_url(message.thread)
    else:
        return conversation_url(message.conversation, message.author)


def conversation_url(conversation, user):
    type = conversation.type()
    if type == "group":
        return group_wall_url(conversation.target)
    elif type == "place":
        return place_wall_url(conversation.target)
    elif type == "activity":
        return activity_detail_url(conversation.target)
    elif type == "private":
        return user_detail_url(user)
    elif type == "application":
        return application_url(conversation.target)
    elif type == "issue":
        return issue_chat_url(conversation.target)
    elif type == "offer":
        return offer_url(conversation.target)
    elif type is None:
        return None

    raise Exception(f"conversation url with type {type} is not defined")


def place_url(place):
    return f"{settings.HOSTNAME}/#/group/{place.group.id}/place/{place.id}/activities"


def user_url(user):
    return f"{settings.HOSTNAME}/#/user/{user.id}"


def history_url(history_id):
    return f"{settings.HOSTNAME}/#/history/{history_id}"


def absolute_url(path):
    if re.match(r"https?:", path):
        return path
    return f"{settings.HOSTNAME}{path}"


def activity_detail_url(activity):
    place = activity.place
    group = place.group
    return f"{settings.HOSTNAME}/#/group/{group.id}/place/{place.id}/activities/{activity.id}/detail"


def activity_notification_unsubscribe_url(user, group):
    return unsubscribe_url(user, group, notification_type=GroupNotificationType.DAILY_ACTIVITY_NOTIFICATION)


def group_summary_unsubscribe_url(user, group):
    return unsubscribe_url(user, group, notification_type=GroupNotificationType.WEEKLY_SUMMARY)


def new_application_unsubscribe_url(user, application):
    return unsubscribe_url(
        user,
        group=application.group,
        conversation=application.conversation,
        notification_type=GroupNotificationType.NEW_APPLICATION,
    )


def new_offer_unsubscribe_url(user, offer):
    return unsubscribe_url(
        user,
        group=offer.group,
        notification_type=GroupNotificationType.NEW_OFFER,
    )


def user_photo_url(user):
    if not user or not user.photo:
        return None
    return "".join([settings.HOSTNAME, user.photo.url])


def group_photo_url(group):
    if not group or not group.photo:
        return None
    return f"{settings.HOSTNAME}/api/groups-info/{group.id}/photo/"


def karrot_logo_url():
    return settings.KARROT_LOGO


def group_photo_or_karrot_logo_url(group):
    return group_photo_url(group) or karrot_logo_url()


def offer_image_url(offer):
    image = offer.images.first()
    if not image:
        return None
    return f"{settings.HOSTNAME}/api/offers/{offer.id}/image/"


def conflict_resolution_unsubscribe_url(user, issue):
    return unsubscribe_url(
        user,
        group=issue.group,
        conversation=issue.conversation,
        notification_type=GroupNotificationType.CONFLICT_RESOLUTION,
    )


def application_url(application):
    return f"{settings.HOSTNAME}/#/group/{application.group.id}/applications/{application.id}"


def offer_url(offer):
    return f"{settings.HOSTNAME}/#/group/{offer.group.id}/offers/{offer.id}"


def issue_url(issue):
    return f"{settings.HOSTNAME}/#/group/{issue.group.id}/issues/{issue.id}"


def issue_chat_url(issue):
    return issue_url(issue) + "/chat"


def user_detail_url(user):
    return f"{settings.HOSTNAME}/#/user/{user.id}/detail"


def thread_url(thread):
    # there should _always_ be a group, the types of conversations that don't have one, don't have threads...
    group = thread.conversation.find_group()
    if not group:
        raise Exception(f"cannot find group for thread: {thread.id}")
    return f"{settings.HOSTNAME}/#/group/{group.id}/message/{thread.id}/replies"


def thread_unsubscribe_url(user, group, thread):
    return unsubscribe_url(user, group, thread=thread)


def group_wall_url(group):
    return f"{settings.HOSTNAME}/#/group/{group.id}/wall"


def place_wall_url(place):
    return f"{settings.HOSTNAME}/#/group/{place.group.id}/place/{place.id}/wall"


def applications_url(group):
    return f"{settings.HOSTNAME}/#/group/{group.id}/applications"


def group_preview_url(group):
    return f"{settings.HOSTNAME}/#/groupPreview/{group.id}"


def group_edit_url(group):
    return f"{settings.HOSTNAME}/#/group/{group.id}/edit"


def conversation_unsubscribe_url(user, conversation, group=None):
    return unsubscribe_url(user, group=group, conversation=conversation)


def unsubscribe_url(user, group=None, conversation=None, thread=None, notification_type=None):
    return "{hostname}/#/unsubscribe/{token}".format(
        hostname=settings.HOSTNAME,
        token=generate_token(
            user,
            group=group,
            conversation=conversation,
            thread=thread,
            notification_type=notification_type,
        ),
    )


def group_settings_url(group):
    return f"{settings.HOSTNAME}/#/group/{group.id}/settings"


def invite_url(invitation):
    invite_url = furl(f"{settings.HOSTNAME}/#/signup")
    invite_url.fragment.args = {"invite": invitation.token, "email": invitation.email}
    return invite_url


def user_delete_url(code):
    return f"{settings.HOSTNAME}/#/delete-user?code={code}"


def user_emailverification_url(code):
    return f"{settings.HOSTNAME}/#/email/verify?code={code}"


def user_passwordreset_url(code):
    return f"{settings.HOSTNAME}/#/password/reset?code={code}"


def logo_url():
    return f"{settings.HOSTNAME}/statics/carrot_logo.png"
