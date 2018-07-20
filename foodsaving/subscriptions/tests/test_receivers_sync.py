import asyncio
import concurrent

import pytest
import threading
from asgiref.sync import AsyncToSync, SyncToAsync
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from concurrent.futures import Executor, Future
from dateutil.parser import parse
from django.db import close_old_connections

from foodsaving.conversations.factories import AsyncConversationFactory, ConversationFactory
from foodsaving.conversations.models import ConversationMessage
from foodsaving.subscriptions.consumers import SyncWebsocketConsumer, WebsocketConsumer, AsyncWebsocketConsumer
from foodsaving.users.factories import AsyncUserFactory, UserFactory


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


class SameThreadExecutor(Executor):

    def submit(self, fn, *args, **kwargs):
        result = Future()
        try:
            result = fn(*args, **kwargs)
        except Exception as e:
            result.set_exception(e)
        else:
            result.set_result(result)
        return result


class SyncWebsocketCommunicator:

    def __init__(self, *args, **kwargs):

        loop = asyncio.get_event_loop()
        loop.__foo = 'I am oijsefosije'
        loop.set_default_executor(SameThreadExecutor())

        #setattr(SyncToAsync.threadlocal, "main_event_loop", loop)

        self.loop = loop

        #del kwargs['loop']
        self.communicator = WebsocketCommunicator(*args, **kwargs)
        self.scope = self.communicator.scope

    def connect(self, *args, **kwargs):
        return self._run_async(self.communicator.connect, args, kwargs)

    def disconnect(self, *args, **kwargs):
        return self._run_async(self.communicator.disconnect, args, kwargs)

    def _run_async(self, awaitable, args, kwargs):
        call_result = asyncio.Future()
        print('loop is running?', self.loop.is_running())
        thing = self._main_wrap(awaitable, args, kwargs, call_result)
        print('thing is', thing)
        self.loop.run_until_complete(thing)
        print('after run_until_complete')
        return call_result.result()

    async def _main_wrap(self, awaitable, args, kwargs, call_result):
        try:
            result = await awaitable(*args, **kwargs)
        except Exception as e:
            call_result.set_exception(e)
        else:
            call_result.set_result(result)

@pytest.fixture
def communicator():
    communicator = SyncWebsocketCommunicator(WebsocketConsumer, '/')
    yield communicator
    # communicator.disconnect()


author_communicator = communicator

create_message = ConversationMessage.objects.create


def get_participant(conversation, user):
    return conversation.conversationparticipant_set.get(user=user)


@pytest.mark.django_db
class TestConversationReceiver:
    def test_receives_messages(self, communicator, author_communicator):
        user = UserFactory()
        print('created use in thread', threading.get_ident())
        author = UserFactory()

        # join a conversation
        conversation = ConversationFactory(participants=[user, author])

        # login and connect

        communicator.scope['user'] = user
        communicator.connect()

        # author_communicator.scope['user'] = author
        # async_to_sync(author_communicator.connect)()
        #
        # # add a message to the conversation
        # message = create_message(conversation=conversation, content='yay', author=author)
        #
        # # hopefully they receive it!
        # response = async_to_sync(communicator.receive_json_from)()
        # parse_dates(response)
        # assert response == make_conversation_message_broadcast(message)
        #
        # # and they should get an updated conversation object
        # response = async_to_sync(communicator.receive_json_from)()
        # parse_dates(response)
        # del response['payload']['participants']
        # assert response == make_conversation_broadcast(conversation, unread_message_count=1)
        #
        # # author should get message & updated conversations object too
        # response = async_to_sync(author_communicator.receive_json_from)()
        # parse_dates(response)
        # assert response == make_conversation_message_broadcast(message, is_editable=True)
        #
        # # Author receives more recent `update_at` time,
        # # because their `seen_up_to` status is set after sending the message.
        # author_participant = get_participant(conversation, author)
        # response = async_to_sync(author_communicator.receive_json_from)()
        # parse_dates(response)
        # del response['payload']['participants']
        # assert response == make_conversation_broadcast(
        #     conversation,
        #     seen_up_to=message.id,
        #     updated_at=author_participant.updated_at,
        # )
