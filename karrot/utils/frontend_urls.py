from furl import furl

from config import settings
from karrot.groups.models import GroupNotificationType
from karrot.unsubscribe.utils import generate_token


def conversation_url(conversation, user):
    type = conversation.type()
    if type == 'group':
        return group_wall_url(conversation.target)
    elif type == 'place':
        return place_wall_url(conversation.target)
    elif type == 'pickup':
        return pickup_detail_url(conversation.target)
    elif type == 'private':
        return user_detail_url(user)
    elif type == 'application':
        return application_url(conversation.target)
    elif type == 'issue':
        return issue_chat_url(conversation.target)
    elif type is None:
        return None

    raise Exception('conversation url with type {} is not defined'.format(type))


def place_url(place):
    return '{hostname}/#/group/{group_id}/place/{place_id}/pickups'.format(
        hostname=settings.HOSTNAME,
        group_id=place.group.id,
        place_id=place.id,
    )


def user_url(user):
    return '{hostname}/#/user/{user_id}/'.format(
        hostname=settings.HOSTNAME,
        user_id=user.id,
    )


def pickup_detail_url(pickup):
    place = pickup.place
    group = place.group
    return '{hostname}/#/group/{group_id}/place/{place_id}/pickups/{pickup_id}/detail'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
        place_id=place.id,
        pickup_id=pickup.id,
    )


def weekly_summary_unsubscribe_url(user, group):
    return unsubscribe_url(user, group, notification_type=GroupNotificationType.WEEKLY_SUMMARY)


def group_summary_unsubscribe_url(user, group):
    return unsubscribe_url(user, group, notification_type=GroupNotificationType.WEEKLY_SUMMARY)


def new_application_unsubscribe_url(user, application):
    return unsubscribe_url(
        user,
        group=application.group,
        conversation=application.conversation,
        notification_type=GroupNotificationType.NEW_APPLICATION,
    )


def conflict_resolution_unsubscribe_url(user, issue):
    return unsubscribe_url(
        user,
        group=issue.group,
        conversation=issue.conversation,
        notification_type=GroupNotificationType.CONFLICT_RESOLUTION,
    )


def application_url(application):
    return '{hostname}/#/group/{group_id}/applications/{application_id}'.format(
        hostname=settings.HOSTNAME,
        group_id=application.group.id,
        application_id=application.id,
    )


def issue_url(issue):
    return '{hostname}/#/group/{group_id}/issues/{issue_id}'.format(
        hostname=settings.HOSTNAME,
        group_id=issue.group.id,
        issue_id=issue.id,
    )


def issue_chat_url(issue):
    return issue_url(issue) + '/chat'


def user_detail_url(user):
    return '{hostname}/#/user/{user_id}/detail'.format(
        hostname=settings.HOSTNAME,
        user_id=user.id,
    )


def thread_url(thread):
    """
    Assumes that thread.conversation.target is a group
    """
    return '{hostname}/#/group/{group_id}/message/{message_id}/replies'.format(
        hostname=settings.HOSTNAME,
        group_id=thread.conversation.target_id,
        message_id=thread.id,
    )


def thread_unsubscribe_url(user, group, thread):
    return unsubscribe_url(user, group, thread=thread)


def group_wall_url(group):
    return '{hostname}/#/group/{group_id}/wall'.format(hostname=settings.HOSTNAME, group_id=group.id)


def place_wall_url(place):
    return '{hostname}/#/group/{group_id}/place/{place_id}/wall'.format(
        hostname=settings.HOSTNAME, group_id=place.group.id, place_id=place.id
    )


def applications_url(group):
    return '{hostname}/#/group/{group_id}/applications'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
    )


def group_edit_url(group):
    return '{hostname}/#/group/{group_id}/edit'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
    )


def conversation_unsubscribe_url(user, conversation, group=None):
    return unsubscribe_url(user, group=group, conversation=conversation)


def unsubscribe_url(user, group=None, conversation=None, thread=None, notification_type=None):
    return '{hostname}/#/unsubscribe/{token}'.format(
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
    return '{hostname}/#/group/{group_id}/settings'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
    )


def invite_url(invitation):
    invite_url = furl('{hostname}/#/signup'.format(hostname=settings.HOSTNAME))
    invite_url.fragment.args = {'invite': invitation.token, 'email': invitation.email}
    return invite_url


def user_delete_url(code):
    return '{hostname}/#/delete-user?code={code}'.format(hostname=settings.HOSTNAME, code=code)


def user_emailverification_url(code):
    return '{hostname}/#/email/verify?code={code}'.format(hostname=settings.HOSTNAME, code=code)


def user_passwordreset_url(code):
    return '{hostname}/#/password/reset?code={code}'.format(hostname=settings.HOSTNAME, code=code)


def logo_url():
    return '{hostname}/statics/carrot_logo.png'.format(hostname=settings.HOSTNAME, )
