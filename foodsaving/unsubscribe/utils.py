from django.contrib.auth import get_user_model
from django.core import signing

from foodsaving.conversations.models import ConversationThreadParticipant, ConversationParticipant, ConversationMessage


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
    data = signing.loads(token)
    user = get_user_model().objects.get(pk=data['u'])
    result = {'user': user}

    if 'g' in data:
        result.update({'group': user.groups.get(pk=data['g'])})

    if 'c' in data:
        result.update({'conversation': user.conversation_set.get(pk=data['c'])})

    if 't' in data:
        result.update({'thread': ConversationMessage.objects.only_threads_with_user(user).get(pk=data['t'])})

    return result


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

    def is_related(conversation):
        """
        check if the conversation targets' related group is our intended group

        each conversation target must implement a group attribute
        """
        target = conversation.target
        return target is not None and target.group == group

    # load all the users conversations
    conversation_ids = [conversation.id for conversation in user.conversation_set.all() if is_related(conversation)]

    # disable email notifications for all these conversations
    ConversationParticipant.objects.filter(
        user=user,
        conversation_id__in=conversation_ids,
    ).update(
        email_notifications=False,
    )

    # ... and mute any threads
    ConversationThreadParticipant.objects.filter(
        user=user,
        thread__conversation_id__in=conversation_ids,
    ).update(
        muted=True,
    )
