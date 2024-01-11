import re
from typing import List, Optional

from django.conf import settings

from karrot.activities.models import Activity
from karrot.groups.models import Group
from karrot.meet.models import Room
from karrot.places.models import Place
from karrot.users.models import User

# room subject pattern e.g. "activity:5" or "group:6" or "user:6346,43,535"
room_subject_re = re.compile("^(?P<subject_type>[a-z]+):(?P<subject_ids>[0-9,]+)$")


def parse_room_subject(room_subject: str) -> Optional[tuple[str, List[int]]]:
    match = room_subject_re.match(room_subject)
    if not match:
        return None

    subject_type = match.group("subject_type")
    subject_ids = match.group("subject_ids")

    # can have multiple ids, sort them so it doesn't matter what order the client sends them in
    subject_ids = sorted([int(val) for val in subject_ids.split(",")])

    return subject_type, subject_ids


def require_room_subject(room_subject: str) -> tuple[str, List[int]]:
    subject_type, subject_ids = parse_room_subject(room_subject)
    if not subject_type:
        raise ValueError("invalid room subject")
    return subject_type, subject_ids


def user_has_room_access(user: User, room_subject: str) -> bool:
    subject_type, subject_ids = parse_room_subject(room_subject)
    if not subject_type:
        return False

    # subject types that require 1 id
    if subject_type in ("group", "place", "activity"):
        if len(subject_ids) != 1:
            return False
        subject_id = subject_ids[0]
        # response_data["subject_id"] = subject_id
        if subject_type == "group":
            return Group.objects.filter(id=subject_id, members=user).exists()
        elif subject_type == "place":
            return Place.objects.filter(id=subject_id, group__members=user).exists()
        elif subject_type == "activity":
            return Activity.objects.filter(id=subject_id, place__group__members=user).exists()
    elif subject_type == "user":
        # response_data["subject_ids"] = subject_ids
        user_ids = list(
            User.objects.filter(id__in=subject_ids, groups__in=user.groups.all())
            .order_by("id")
            .values_list("id", flat=True)
        )
        return user_ids == subject_ids

    return False


def get_room_group(room_subject: str) -> Optional[Group]:
    subject_type, subject_ids = parse_room_subject(room_subject)
    if not subject_type:
        return None
    if subject_type in ("group", "place", "activity"):
        subject_id = subject_ids[0]
        if subject_type == "group":
            return Group.objects.get(id=subject_id)
        elif subject_type == "place":
            return Group.objects.get(places=subject_id)
        elif subject_type == "activity":
            return Group.objects.get(places__activities=subject_id)
    return None


def get_or_create_room(room_subject: str) -> Room:
    subject_type, subject_ids = require_room_subject(room_subject)
    group = get_room_group(room_subject)
    room, created = Room.objects.get_or_create(group=group, subject=room_subject)
    if created and subject_type == "user":
        room.subject_users.add(*User.objects.filter(id__in=subject_ids))
    return room


def room_subject_to_room_name(room_subject: str) -> str:
    return f"{settings.MEET_LIVEKIT_ROOM_PREFIX}{room_subject}"
