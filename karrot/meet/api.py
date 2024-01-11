import json

from django.conf import settings
from django.db import transaction
from rest_framework import status
from rest_framework.generics import GenericAPIView
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.response import Response

from karrot.meet.livekit import create_room_token, list_participants, webhook_receiver
from karrot.meet.meet_utils import (
    get_or_create_room,
    parse_room_subject,
    room_subject_to_room_name,
    user_has_room_access,
)
from karrot.meet.models import Room
from karrot.meet.serializers import RoomSerializer
from karrot.meet.tasks import notify_room_changed, notify_room_ended
from karrot.users.models import User


class NotFoundResponse(Response):
    def __init__(self):
        super().__init__({}, status=404)


class MeetViewSet(GenericAPIView):
    def get(self, request):
        """Creates a room token for a given room subject

        Allows the user with the token to join that room
        """
        room_subject = request.query_params.get("subject", None)
        if not room_subject:
            return NotFoundResponse()

        if not settings.MEET_LIVEKIT_API_KEY or not settings.MEET_LIVEKIT_API_SECRET:
            return NotFoundResponse()

        user = request.user
        if not user or user.is_anonymous:
            return NotFoundResponse()

        subject_type, subject_ids = parse_room_subject(room_subject)

        if not subject_type:
            return NotFoundResponse()

        if not user_has_room_access(user, room_subject):
            return NotFoundResponse()

        return Response(
            {
                "subject": room_subject,
                "token": create_room_token(user, room_subject),
            }
        )


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
        if not event.room.name.startswith(settings.MEET_LIVEKIT_ROOM_PREFIX):
            # not our prefix, ignore...
            return Response(status=status.HTTP_200_OK)

        room_subject = event.room.name.removeprefix(settings.MEET_LIVEKIT_ROOM_PREFIX)

        subject_type, subject_ids = parse_room_subject(room_subject)
        if not subject_type:
            # didn't match our format, ignore it
            return Response(status=status.HTTP_200_OK)

        # Don't actually need to handle "room_started" as
        # we get a "participant_joined" right after, and we can just
        # sync everything then.

        if event.event == "room_finished":
            room = Room.objects.filter(subject=room_subject).first()
            if room:
                notify_room_ended(RoomSerializer(room).data)
                room.delete()
        elif event.event == "participant_joined":
            sync_participants_and_notify(room_subject)
        elif event.event == "participant_left":
            sync_participants_and_notify(room_subject)

        return Response(status=status.HTTP_200_OK)


def sync_participants_and_notify(room_subject: str):
    """Fetch and sync participants then notify users

    Lists the participants using the livekit server API
    then updates our database to match.

    Means we don't need to rely on keeping track of join/left participants
    and will always ensure it's correct.
    """
    with transaction.atomic():
        room = get_or_create_room(room_subject)
        participants = {participant.identity: participant for participant in room.participants.all()}
        for livekit_participant in list_participants(room_subject_to_room_name(room_subject)):
            participant = participants.pop(livekit_participant.identity, None)
            if not participant:
                metadata = json.loads(livekit_participant.metadata)
                user = None
                if "user_id" in metadata:
                    user = User.objects.get(id=metadata["user_id"])
                room.participants.create(identity=livekit_participant.identity, user=user)
        # anything leftover is no longer in room
        [participant.delete() for participant in participants.values()]
    notify_room_changed(RoomSerializer(room).data)
