from furl import furl

from config import settings
from foodsaving.unsubscribe.utils import generate_token


def conversation_url(conversation, user):
    type = conversation.type()
    if type == 'group':
        return group_wall_url(conversation.target)
    elif type == 'pickup':
        return pickup_detail_url(conversation.target)
    elif type == 'private':
        return user_detail_url(user)
    elif type == 'application':
        return group_application_url(conversation.target)
    return None


def store_url(store):
    return '{hostname}/#/group/{group_id}/store/{store_id}/pickups'.format(
        hostname=settings.HOSTNAME,
        group_id=store.group.id,
        store_id=store.id,
    )


def user_url(user):
    return '{hostname}/#/user/{user_id}/'.format(
        hostname=settings.HOSTNAME,
        user_id=user.id,
    )


def pickup_detail_url(pickup):
    store = pickup.store
    group = store.group
    return '{hostname}/#/group/{group_id}/store/{store_id}/pickups/{pickup_id}/detail'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
        store_id=store.id,
        pickup_id=pickup.id,
    )


def pickup_conversation_mute_url(user, pickup, conversation):
    return unsubscribe_url(user, pickup.store.group, conversation=conversation)


def group_application_url(application):
    return '{hostname}/#/group/{group_id}/applications/{application_id}'.format(
        hostname=settings.HOSTNAME,
        group_id=application.group.id,
        application_id=application.id,
    )


def group_application_mute_url(user, application, conversation):
    return unsubscribe_url(user, application.group, conversation=conversation)


def user_detail_url(user):
    return '{hostname}/#/user/{user_id}/detail'.format(
        hostname=settings.HOSTNAME,
        user_id=user.id,
    )


def user_conversation_mute_url(user, conversation):
    return '{}?mute_conversation={}'.format(user_detail_url(user), conversation.id)


def thread_url(thread):
    """
    Assumes that thread.conversation.target is a group
    """
    return '{hostname}/#/group/{group_id}/message/{message_id}/replies'.format(
        hostname=settings.HOSTNAME,
        group_id=thread.conversation.target_id,
        message_id=thread.id,
    )


def thread_mute_url(user, group, thread):
    return unsubscribe_url(user, group, thread=thread)


def group_wall_url(group):
    return '{hostname}/#/group/{group_id}/wall'.format(hostname=settings.HOSTNAME, group_id=group.id)


def group_applications_url(group):
    return '{hostname}/#/group/{group_id}/applications'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
    )


def group_edit_url(group):
    return '{hostname}/#/group/{group_id}/edit'.format(
        hostname=settings.HOSTNAME,
        group_id=group.id,
    )


def group_conversation_mute_url(user, group, conversation):
    return unsubscribe_url(user, group, conversation=conversation)


def unsubscribe_url(user, group, conversation=None, thread=None):
    return '{hostname}/#/unsubscribe/{token}'.format(
        hostname=settings.HOSTNAME,
        token=generate_token(
            user,
            group,
            conversation=conversation,
            thread=thread,
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
