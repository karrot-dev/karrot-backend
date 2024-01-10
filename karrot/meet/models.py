from django.conf import settings
from django.db import models
from django.db.models import CharField, ForeignKey

from karrot.base.base_models import BaseModel


class Room(BaseModel):
    name = CharField(unique=True, max_length=255)


class RoomParticipant(BaseModel):
    room = ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    identity = CharField(unique=True)
    user = ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
    )
