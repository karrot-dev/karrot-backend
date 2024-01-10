from asgiref.sync import async_to_sync
from django.conf import settings
from livekit.api import LiveKitAPI
from livekit.protocol.room import ListParticipantsRequest


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
