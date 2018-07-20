from furl import furl

from config import settings
from foodsaving.groups.models import Group
from foodsaving.pickups.models import PickupDate


def conversation_url(conversation, user):
    if isinstance(conversation.target, Group):
        return group_wall_url(conversation.target)
    elif isinstance(conversation.target, PickupDate):
        return pickup_detail_url(conversation.target)
    elif conversation.is_private:
        return user_detail_url(user)
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


def pickup_conversation_mute_url(pickup, conversation):
    return '{}?mute_conversation={}'.format(pickup_detail_url(pickup), conversation.id)


def group_application_url(application):
    # TODO check before merging
    return '{hostname}/#/group/{group_id}/applications/{application_id}/'.format(
        hostname=settings.HOSTNAME,
        group_id=application.group.id,
        application_id=application.id,
    )


def group_application_mute_url(application, conversation):
    return '{}?mute_conversation={}'.format(group_application_url(application), conversation.id)


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


def thread_mute_url(thread):
    return '{}?mute'.format(thread_url(thread))


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


def group_conversation_mute_url(group, conversation):
    return '{}?mute_conversation={}'.format(group_wall_url(group), conversation.id)


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
