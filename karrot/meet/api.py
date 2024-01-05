import json
import re
from datetime import timedelta

from django.utils.crypto import get_random_string
from livekit.api import AccessToken, VideoGrants
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from karrot.activities.models import Activity
from karrot.groups.models import Group
from karrot.places.models import Place

# room id pattern e.g. "activity:5" or "group:6"
room_id_re = re.compile("^(?P<subject_type>[a-z]+):(?P<subject_id>[0-9]+)$")


class NotFoundResponse(Response):
    def __init__(self):
        super().__init__({}, status=404)


class MeetViewSet(GenericAPIView):
    def get(self, request, room_id):
        """Creates a room token for a given room_id

        Allows the user with the token to join that room
        """
        user = request.user
        if not user or user.is_anonymous:
            return NotFoundResponse()

        match = room_id_re.match(room_id)
        if not match:
            return NotFoundResponse()

        subject_type = match.group("subject_type")
        subject_id = match.group("subject_id")

        room_subject = None

        if subject_type == "group":
            room_subject = Group.objects.filter(id=subject_id, members=user).first()
        elif subject_type == "place":
            room_subject = Place.objects.filter(id=subject_id, group__members=user).first()
        elif subject_type == "activity":
            room_subject = Activity.objects.filter(id=subject_id, place__group__members=user).first()

        if not room_subject:
            return NotFoundResponse()

        # TODO: might be nice to base it on the session id, or store a "meet identity" in the session
        # then there is only one per user session... this is probably fine at the moment though
        identity = get_random_string(length=20)
        token = (
            # TODO: put api_key/api_secret in settings/config
            AccessToken("devkey", "secret")
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
                    room=room_id,
                )
            )
        )

        return Response(
            {
                "room_id": room_id,
                "subject_type": subject_type,
                "subject_id": subject_id,
                "token": token.to_jwt(),
            }
        )
