import json
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils.crypto import get_random_string
from livekit.api import AccessToken, TokenVerifier, VideoGrants, WebhookReceiver
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.response import Response

from karrot.activities.models import Activity
from karrot.groups.models import Group
from karrot.meet.livekit import list_participants
from karrot.meet.meet_utils import parse_room_name
from karrot.meet.models import Room
from karrot.meet.tasks import notify_room_changed, notify_room_ended
from karrot.places.models import Place
from karrot.users.models import User


class NotFoundResponse(Response):
    def __init__(self):
        super().__init__({}, status=404)


class MeetViewSet(GenericAPIView):
    def get(self, request, room_name):
        """Creates a room token for a given room_id

        Allows the user with the token to join that room
        """
        api_key = settings.MEET_LIVEKIT_API_KEY
        api_secret = settings.MEET_LIVEKIT_API_SECRET
        if not api_key or not api_secret:
            return NotFoundResponse()

        user = request.user
        if not user or user.is_anonymous:
            return NotFoundResponse()

        subject_type, subject_ids = parse_room_name(room_name)

        if not subject_type:
            return NotFoundResponse()

        extra_response_data = {"subject_type": subject_type}

        # subject types that require 1 id
        if subject_type in ("group", "place", "activity"):
            if len(subject_ids) != 1:
                return NotFoundResponse()
            subject_id = subject_ids[0]
            extra_response_data["subject_id"] = subject_id
            if subject_type == "group":
                if not Group.objects.filter(id=subject_id, members=user).exists():
                    return NotFoundResponse()
            elif subject_type == "place":
                if not Place.objects.filter(id=subject_id, group__members=user).exists():
                    return NotFoundResponse()
            elif subject_type == "activity":
                if not Activity.objects.filter(id=subject_id, place__group__members=user).exists():
                    return NotFoundResponse()
        elif subject_type == "user":
            extra_response_data["subject_ids"] = subject_ids
            user_ids = list(
                User.objects.filter(id__in=subject_ids, groups__in=self.request.user.groups.all())
                .order_by("id")
                .values_list("id", flat=True)
            )
            if user_ids != subject_ids:
                return NotFoundResponse()
        else:
            return NotFoundResponse()
        # TODO: could have an application chat one too!

        # TODO: might be nice to base it on the session id, or store a "meet identity" in the session
        # then there is only one per user session... this is probably fine at the moment though
        identity = get_random_string(length=20)
        token = (
            AccessToken(api_key, api_secret)
            .with_identity(identity)
            # we set metadata which allows the other participants to be looked up by id
            .with_metadata(
                json.dumps(
                    {
                        "user_id": user.id,
                    }
                )
            )
            # time to use the token, expected to use it immediately
            .with_ttl(timedelta(seconds=20))
            .with_grants(
                VideoGrants(
                    room_join=True,
                    room=room_name,
                )
            )
        )

        return Response(
            {
                "room_name": room_name,
                "token": token.to_jwt(),
                **extra_response_data,
            }
        )


token_verifier = TokenVerifier(
    settings.MEET_LIVEKIT_API_KEY,
    settings.MEET_LIVEKIT_API_SECRET,
)
webhook_receiver = WebhookReceiver(token_verifier)


class LiveKitContentNegotiation(BaseContentNegotiation):
    def select_parser(self, request, parsers):
        for parser in parsers:
            if parser.media_type == "application/json":
                return parser

    def select_renderer(self, request, renderers, format_suffix=None):
        for renderer in renderers:
            if renderer.media_type == "application/json":
                return renderer, renderer.media_type


# application/webhook+json


class MeetWebhookViewSet(GenericAPIView):
    """Receive livekit webhooks

    See docs at https://docs.livekit.io/realtime/server/webhooks/
    """

    # if sends us "application/webhook+json" so we need to fiddle with the negotiation part
    content_negotiation_class = LiveKitContentNegotiation

    def post(self, request):
        auth_token = request.headers.get("Authorization")
        if not auth_token:
            return Response(status=status.HTTP_401_UNAUTHORIZED)
        event = webhook_receiver.receive(request.body.decode("utf-8"), auth_token)
        subject_type, subject_ids = parse_room_name(event.room.name)
        if not subject_type:
            # didn't match our format, ignore it
            return Response(status=status.HTTP_200_OK)

        # Don't actually need to handle "room_started" as
        # we get a "participant_joined" right after, and we can just
        # sync everything then.

        # if event.event == "room_started":
        #     sync_participants_and_notify(event.room.name)
        if event.event == "room_finished":
            room = Room.objects.get(name=event.room.name)
            room_name = room.name
            room.delete()
            notify_room_ended(room_name)
        elif event.event == "participant_joined":
            sync_participants_and_notify(event.room.name)
        elif event.event == "participant_left":
            sync_participants_and_notify(event.room.name)

        return Response(status=status.HTTP_200_OK)


def sync_participants_and_notify(room_name: str):
    """Fetch and sync participants then notify users

    Lists the participants using the livekit server API
    then updates our database to match.

    Means we don't need to rely on keeping track of join/left participants
    and will always ensure it's correct.
    """
    with transaction.atomic():
        room, _ = Room.objects.get_or_create(name=room_name)
        participants = {participant.identity: participant for participant in room.participants.all()}
        for livekit_participant in list_participants(room_name):
            participant = participants.pop(livekit_participant.identity, None)
            if not participant:
                metadata = json.loads(livekit_participant.metadata)
                user = None
                if "user_id" in metadata:
                    user = User.objects.get(id=metadata["user_id"])
                room.participants.create(identity=livekit_participant.identity, user=user)
        # anything leftover is no longer in room
        [participant.delete() for participant in participants.values()]
    notify_room_changed(room)
