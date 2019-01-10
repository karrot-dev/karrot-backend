from django.contrib.contenttypes.models import ContentType
from django.core import signing

from foodsaving.conversations.models import ConversationThreadParticipant, ConversationParticipant
from foodsaving.pickups.models import PickupDate


def generate_token(user, group=None, conversation=None, thread=None):
    data = {'u': user.id}
    if group:
        data.update({
            'g': group.id,
            'gn': group.name,
        })
    if conversation:
        data.update({'c': conversation.id})
    elif thread:
        if not thread.is_first_in_thread():
            raise Exception('your thread is not a thread!')
        data.update({'t': thread.id})
    return signing.dumps(data)


def parse_token(token):
    return signing.loads(token)


def unsubscribe_from_conversation(user, conversation):
    ConversationParticipant.objects.filter(
        user=user,
        conversation=conversation,
    ).update(
        email_notifications=False,
    )


def unsubscribe_from_thread(user, thread):
    ConversationThreadParticipant.objects.filter(
        user=user,
        thread=thread,
    ).update(
        muted=True,
    )


def unsubscribe_from_all_conversations_in_group(user, group):
    """
    unsubscribe from ALL conversations related to this group
    """

    # wall
    participant = group.conversation.conversationparticipant_set.get(user=user)
    participant.email_notifications = False
    participant.save()

    # wall threads
    ConversationThreadParticipant.objects.filter(
        user=user,
        thread__conversation=group.conversation,
    ).update(
        muted=True,
    )

    # pickup chats
    ConversationParticipant.objects.filter(
        user=user,
        # need to check if these actually are AND'ing... ORing would not be good
        conversation__target_id__in=PickupDate.objects.filter(store__group=group),
        conversation__target_type=ContentType.objects.get_for_model(PickupDate),
    ).update(
        email_notifications=False,
    )

    # group applications
    ConversationParticipant.objects.filter(
        user=user,
        # need to check if these actually are AND'ing... ORing would not be good
        conversation__target_id__in=group.groupapplication_set.values_list('pk', flat=True),
        conversation__target_type=ContentType.objects.get(app_label='applications', model='groupapplication'),
    ).update(
        email_notifications=False,
    )
