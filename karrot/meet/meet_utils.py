import re
from typing import List, Optional

# room id pattern e.g. "activity:5" or "group:6" or "user:6346,43,535"
room_id_re = re.compile("^(?P<subject_type>[a-z]+):(?P<subject_ids>[0-9,]+)$")


def parse_room_name(room_name: str) -> Optional[tuple[str, List[int]]]:
    match = room_id_re.match(room_name)
    if not match:
        return None

    subject_type = match.group("subject_type")
    subject_ids = match.group("subject_ids")

    # can have multiple ids, sort them so it doesn't matter what order the client sends them in
    subject_ids = sorted([int(val) for val in subject_ids.split(",")])

    return subject_type, subject_ids
