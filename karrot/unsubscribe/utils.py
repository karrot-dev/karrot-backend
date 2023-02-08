from django.contrib.auth import get_user_model
from django.core import signing

from karrot.conversations.models import ConversationThreadParticipant, ConversationParticipant, ConversationMessage
from karrot.groups.models import GroupMembership


def generate_token(user, group=None, conversation=None, thread=None, notification_type=None):
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
    if notification_type:
        data.update({'n': notification_type})
    return signing.dumps(data)


def parse_token(token):
    data = signing.loads(token)
    user = get_user_model().objects.get(pk=data['u'])
    result = {'user': user}

    if 'g' in data:
        result.update({'group': user.groups.get(pk=data['g'])})

    if 'c' in data:
        result.update({'conversation': user.conversation_set.get(pk=data['c'])})

    if 't' in data:
        result.update({'thread': ConversationMessage.objects.only_threads_with_user(user).get(pk=data['t'])})

    if 'n' in data:
        result.update({'notification_type': data['n']})

    return result


def unsubscribe_from_conversation(user, conversation):
    p = ConversationParticipant.objects.filter(
        user=user,
        conversation=conversation,
    ).first()
    if p:
        p.muted = True
        p.save()


def unsubscribe_from_thread(user, thread):
    p = ConversationThreadParticipant.objects.filter(
        user=user,
        thread=thread,
    ).first()
    if p:
        p.muted = True
        p.save()


def unsubscribe_from_notification_type(user, group, notification_type):
    membership = group.groupmembership_set.get(user=user)
    membership.remove_notification_types([notification_type])
    membership.save()


def unsubscribe_from_all_conversations_in_group(user, group):
    """
    unsubscribe from ALL conversations related to this group
    """

    # load related conversations
    conversations = user.conversation_set.filter(group=group)

    # disable email notifications for all these conversations
    conversation_count = 0
    for p in ConversationParticipant.objects.filter(
            user=user,
            conversation__in=conversations,
            muted=False,
    ):
        p.muted = True
        p.save()
        conversation_count += 1

    # ... and mute any threads
    thread_count = 0
    for p in ConversationThreadParticipant.objects.filter(
            user=user,
            thread__conversation__in=conversations,
            muted=False,
    ):
        p.muted = True
        p.save()
        thread_count += 1

    # save them from these notifications too
    membership = GroupMembership.objects.get(
        group=group,
        user=user,
    )
    membership.notification_types = []
    membership.save()

    return {
        'conversations': conversation_count,
        'threads': thread_count,
    }
