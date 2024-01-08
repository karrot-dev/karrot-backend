import json
import re
from datetime import timedelta

from django.conf import settings
from django.utils.crypto import get_random_string
from livekit.api import AccessToken, VideoGrants
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response

from karrot.activities.models import Activity
from karrot.groups.models import Group
from karrot.places.models import Place
from karrot.users.models import User

# room id pattern e.g. "activity:5" or "group:6"
room_id_re = re.compile("^(?P<subject_type>[a-z]+):(?P<subject_ids>[0-9,]+)$")


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
        subject_ids = match.group("subject_ids")

        # can have multiple ids, sort them so it doesn't matter what order the client sends them in
        subject_ids = sorted([int(val) for val in subject_ids.split(",")])

        if subject_type == "group" and len(subject_ids) == 1:
            if not Group.objects.filter(id=subject_ids[0], members=user).exists():
                return NotFoundResponse()
        elif subject_type == "place" and len(subject_ids) == 1:
            if not Place.objects.filter(id=subject_ids[0], group__members=user).exists():
                return NotFoundResponse()
        elif subject_type == "activity" and len(subject_ids) == 1:
            if not Activity.objects.filter(id=subject_ids[0], place__group__members=user).exists():
                return NotFoundResponse()
        elif subject_type == "user":
            # user_ids = sorted([int(user_id) for user_id in subject_id.split(",")])
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
            AccessToken(
                settings.MEET_LIVEKIT_API_KEY,
                settings.MEET_LIVEKIT_API_SECRET,
            )
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
                "subject_ids": subject_ids,
                "token": token.to_jwt(),
            }
        )
