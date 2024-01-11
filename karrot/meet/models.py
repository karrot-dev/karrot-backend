from django.conf import settings
from django.db import models
from django.db.models import CharField, ForeignKey

from karrot.base.base_models import BaseModel
from karrot.groups.models import Group
from karrot.users.models import User


class Room(BaseModel):
    group = ForeignKey(
        Group,
        on_delete=models.CASCADE,
        related_name="meet_rooms",
        null=True,  # some rooms are not associated with a group, e.g. user to user rooms
    )
    subject = CharField(unique=True, max_length=255)

    # used for user-to-user rooms
    subject_users = models.ManyToManyField(User)


class RoomParticipant(BaseModel):
    room = ForeignKey(Room, on_delete=models.CASCADE, related_name="participants")
    identity = CharField(unique=True)
    user = ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        null=True,
    )
