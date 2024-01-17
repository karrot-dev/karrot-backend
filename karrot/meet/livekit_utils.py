import json
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import List

from asgiref.sync import async_to_sync
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.utils.crypto import get_random_string
from livekit.api import AccessToken, LiveKitAPI, TokenVerifier, VideoGrants, WebhookReceiver
from livekit.protocol.models import ParticipantInfo
from livekit.protocol.room import CreateRoomRequest, ListParticipantsRequest

from karrot.meet.meet_utils import room_subject_to_room_name
from karrot.meet.models import Room
from karrot.users.models import User


def receive_request(request: HttpRequest):
    auth_token = request.headers.get("Authorization")
    if not auth_token:
        raise PermissionDenied()

    token_verifier = TokenVerifier(
        settings.MEET_LIVEKIT_API_KEY,
        settings.MEET_LIVEKIT_API_SECRET,
    )
    webhook_receiver = WebhookReceiver(token_verifier)

    return webhook_receiver.receive(request.body.decode("utf-8"), auth_token)


def create_room_token(user: User, room_subject: str) -> str:
    # TODO: might be nice to base it on the session id, or store a "meet identity" in the session
    # then there is only one per user session... this is probably fine at the moment though
    identity = get_random_string(length=20)

    token = (
        AccessToken(
            settings.MEET_LIVEKIT_API_KEY,
            settings.MEET_LIVEKIT_API_SECRET,
        )
        .with_identity(identity)
        .with_metadata(
            json.dumps(
                {
                    # we set metadata which allows the other participants to be looked up by id
                    "user_id": user.id,
                }
            )
        )
        # time to use the token, expected to use it immediately
        .with_ttl(timedelta(seconds=20))
        .with_grants(
            VideoGrants(
                room_create=False,
                room_join=True,
                # actual room name as far as livekit is concerned is prefix + subject
                room=room_subject_to_room_name(room_subject),
            )
        )
    )
    return token.to_jwt()


@asynccontextmanager
async def livekit_api():
    # This needs to be run from an async context
    api = LiveKitAPI(
        url=settings.MEET_LIVEKIT_ENDPOINT,
        api_key=settings.MEET_LIVEKIT_API_KEY,
        api_secret=settings.MEET_LIVEKIT_API_SECRET,
    )
    try:
        yield api
    finally:
        await api.aclose()


async def alist_participants(room_name: str) -> List[ParticipantInfo]:
    # Would be nice to have a non-async version
    # TODO: use "twirp" python lib and avoid the async/sync dance?
    # OR could have an async django view (but they're not great as lots of middleware is sync)
    # OR OR could have a fully async path by mounting at the ASGI app layer
    async with livekit_api() as api:
        result = await api.room.list_participants(ListParticipantsRequest(room=room_name))
        return result.participants


async def acreate_room(room_name: str) -> Room:
    async with livekit_api() as api:
        return await api.room.create_room(CreateRoomRequest(name=room_name))


def create_room(room_name: str) -> Room:
    return async_to_sync(acreate_room)(room_name)


def list_participants(room_name: str) -> List[ParticipantInfo]:
    return async_to_sync(alist_participants)(room_name)
