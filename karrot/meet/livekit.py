import json
from datetime import timedelta

from asgiref.sync import async_to_sync
from django.conf import settings
from django.utils.crypto import get_random_string
from livekit.api import AccessToken, LiveKitAPI, TokenVerifier, VideoGrants, WebhookReceiver
from livekit.protocol.room import ListParticipantsRequest

from karrot.meet.meet_utils import room_subject_to_room_name
from karrot.users.models import User

token_verifier = TokenVerifier(
    settings.MEET_LIVEKIT_API_KEY,
    settings.MEET_LIVEKIT_API_SECRET,
)
webhook_receiver = WebhookReceiver(token_verifier)


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
                room_join=True,
                # actual room name as far as livekit is concerned is prefix + subject
                room=room_subject_to_room_name(room_subject),
            )
        )
    )
    return token.to_jwt()


async def alist_participants(room_name: str):
    # Would be nice to have a non-async version
    # TODO: use "twirp" python lib and avoid the async/sync dance?
    # OR could have an async django view (but they're not great as lots of middleware is sync)
    # OR OR could have a fully async path by mounting at the ASGI app layer

    # This needs to be constructed in an async context
    livekit_api = LiveKitAPI(
        url=settings.MEET_LIVEKIT_ENDPOINT,
        api_key=settings.MEET_LIVEKIT_API_KEY,
        api_secret=settings.MEET_LIVEKIT_API_SECRET,
    )
    result = await livekit_api.room.list_participants(ListParticipantsRequest(room=room_name))
    return result.participants


def list_participants(room_name: str):
    return async_to_sync(alist_participants)(room_name)
