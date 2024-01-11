from rest_framework import serializers

from karrot.meet.models import Room, RoomParticipant


class RoomParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomParticipant
        fields = [
            "identity",
            "user",
        ]


class RoomSerializer(serializers.ModelSerializer):
    participants = RoomParticipantSerializer(many=True)

    class Meta:
        model = Room
        fields = [
            "id",
            "subject",
            "participants",
        ]
