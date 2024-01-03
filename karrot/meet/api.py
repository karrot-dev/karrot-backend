import json

from django.utils.crypto import get_random_string
from livekit.api import AccessToken, VideoGrants
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response


class MeetViewSet(GenericAPIView):
    def get(self, request, room_id):
        """Make a room token"""
        user = request.user
        if not user or user.is_anonymous:
            return Response({}, status=404)

        # TODO: parse room_id and check user has permissions!

        identity = get_random_string(length=20)
        token = (
            AccessToken("devkey", "secret").with_identity(identity).with_name(user.display_name).with_metadata(
                json.dumps({
                    "user_id": user.id,
                })
            ).with_grants(VideoGrants(
                room_join=True,
                room=room_id,
            ))
        )

        return Response({
            "room_id": room_id,
            "token": token.to_jwt(),
        })
