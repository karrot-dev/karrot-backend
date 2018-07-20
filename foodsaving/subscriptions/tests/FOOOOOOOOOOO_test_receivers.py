import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from dateutil.parser import parse

from foodsaving.conversations.factories import AsyncConversationFactory
from foodsaving.conversations.models import ConversationMessage
from foodsaving.subscriptions.consumers import SyncWebsocketConsumer
from foodsaving.users.factories import AsyncUserFactory


def parse_dates(data):
    payload = data['payload']
    for k in ('created_at', 'updated_at'):
        if payload.get(k):
            payload[k] = parse(payload[k])


def make_conversation_message_broadcast(message, **kwargs):
    response = {
        'topic': 'conversations:message',
        'payload': {
            'id': message.id,
            'content': message.content,
            'author': message.author.id,
            'conversation': message.conversation.id,
            'created_at': message.created_at,
            'updated_at': message.updated_at,
            'received_via': '',
            'reactions': [],
            'is_editable': False
        }
    }
    response['payload'].update(kwargs)
    return response


def make_conversation_broadcast(conversation, **kwargs):
    response = {
        'topic': 'conversations:conversation',
        'payload': {
            'id': conversation.id,
            'updated_at': conversation.updated_at,
            'seen_up_to': None,
            'unread_message_count': 0,
            'email_notifications': True,
        }
    }
    response['payload'].update(kwargs)
    return response


async def receive_responses_sorted_by_topic(communicator, count):
    responses = []
    for _ in range(count):
        responses.append(await communicator.receive_json_from(timeout=5))
    return sorted(responses, key=lambda r: r['topic'])


@pytest.fixture
async def communicator():
    communicator = WebsocketCommunicator(SyncWebsocketConsumer, '/')
    yield communicator
    await communicator.disconnect()


author_communicator = communicator

create_message = database_sync_to_async(ConversationMessage.objects.create)


@database_sync_to_async
def get_participant(conversation, user):
    return conversation.conversationparticipant_set.get(user=user)


@pytest.mark.asyncio
@pytest.mark.django_db
class TestConversationReceiver:
    async def test_receives_messages(self, communicator, author_communicator):
        user = await AsyncUserFactory()
        author = await AsyncUserFactory()

        # join a conversation
        conversation = await AsyncConversationFactory(participants=[user, author])

        # login and connect

        communicator.scope['user'] = user
        await communicator.connect()

        author_communicator.scope['user'] = author
        await author_communicator.connect()

        # add a message to the conversation
        message = await create_message(conversation=conversation, content='yay', author=author)

        # hopefully they receive it!
        response = await communicator.receive_json_from()
        parse_dates(response)
        assert response == make_conversation_message_broadcast(message)

        # and they should get an updated conversation object
        response = await communicator.receive_json_from()
        parse_dates(response)
        del response['payload']['participants']
        assert response == make_conversation_broadcast(conversation, unread_message_count=1)

        # author should get message & updated conversations object too
        response = await author_communicator.receive_json_from()
        parse_dates(response)
        assert response == make_conversation_message_broadcast(message, is_editable=True)

        # Author receives more recent `update_at` time,
        # because their `seen_up_to` status is set after sending the message.
        author_participant = await get_participant(conversation, author)
        response = await author_communicator.receive_json_from()
        parse_dates(response)
        del response['payload']['participants']
        assert response == make_conversation_broadcast(
            conversation,
            seen_up_to=message.id,
            updated_at=author_participant.updated_at,
        )

    async def tests_receive_message_on_leave(self, communicator):
        user = await AsyncUserFactory()

        # join a conversation
        conversation = await AsyncConversationFactory(participants=[user])

        # login and connect
        communicator.scope['user'] = user
        await communicator.connect()

        await database_sync_to_async(conversation.leave)(user)

        response = await communicator.receive_json_from()

        assert response == {'topic': 'conversations:leave', 'payload': {'id': conversation.id}}

    async def test_other_participants_receive_update_on_join(self, communicator):
        user = await AsyncUserFactory()
        joining_user = await AsyncUserFactory()

        # join a conversation
        conversation = await AsyncConversationFactory(participants=[
            user,
        ])

        # login and connect
        communicator.scope['user'] = user
        await communicator.connect()

        await database_sync_to_async(conversation.join)(joining_user)

        response = await communicator.receive_json_from()

        assert response['topic'] == 'conversations:conversation'
        assert set(response['payload']['participants']) == {user.id, joining_user.id}

    async def test_other_participants_receive_update_on_leave(self, communicator):
        user = await AsyncUserFactory()
        leaving_user = await AsyncUserFactory()

        # join a conversation
        conversation = await AsyncConversationFactory(participants=[user, leaving_user])

        # login and connect
        communicator.scope['user'] = user
        await communicator.connect()

        await database_sync_to_async(conversation.leave)(leaving_user)

        response = await communicator.receive_json_from()

        assert response['topic'] == 'conversations:conversation'
        assert response['payload']['participants'] == [user.id]
