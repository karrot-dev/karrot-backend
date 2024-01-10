from io import BytesIO
from os.path import join
from tarfile import TarFile, TarInfo
from typing import List

import orjson
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from pytz import BaseTzInfo

from karrot.activities.models import ActivitySeries, ActivityType, Feedback, FeedbackNoShow, SeriesParticipantType
from karrot.groups.models import Group, GroupMembership
from karrot.migrate.serializers import (
    MigrateFileSerializer,
    get_migrate_serializer_class,
)
from karrot.places.models import Place, PlaceStatus, PlaceType


class FakeRequest:
    user = AnonymousUser()


def serialize_value(value):
    if isinstance(value, BaseTzInfo):
        return str(value)
    raise TypeError


def export_to_file(group_ids: List[int], output_filename: str):
    with TarFile.open(output_filename, "w|xz") as tarfile:
        groups = Group.objects.filter(id__in=group_ids)
        if len(groups) != len(group_ids):
            print("Not all groups found")
            return

        fake_request = FakeRequest()
        serializer_context = {"request": fake_request}

        def export_queryset(qs, serializer_class=None):
            if not serializer_class:
                serializer_class = get_migrate_serializer_class(qs.model)
            ct = ContentType.objects.get_for_model(qs.model)
            data_type = f"{ct.app_label}.{ct.model}"
            data = BytesIO()
            for item in qs.order_by("pk").iterator():
                item_data = serializer_class(item, context=serializer_context).data
                data.write(orjson.dumps(item_data, default=serialize_value))
                data.write(b"\n")
            data.seek(0)
            json_info = TarInfo(f"{data_type}.json")
            json_info.size = data.getbuffer().nbytes

            # before exporting the json export any files first
            # so when we import they are already there!
            for file in MigrateFileSerializer.exported_files:
                file_info = TarInfo(join("files", file.name))
                file_info.size = file.size
                tarfile.addfile(file_info, file)
            MigrateFileSerializer.exported_files = []

            tarfile.addfile(json_info, data)

        # users
        # export them first as they are referred to in lots of other things
        export_queryset(get_user_model().objects.filter(groupmembership__group__in=groups))

        # groups
        export_queryset(groups)

        # group memberships
        export_queryset(GroupMembership.objects.filter(group__in=groups))

        # activity types
        export_queryset(ActivityType.objects.filter(group__in=groups))

        # place types
        export_queryset(PlaceType.objects.filter(group__in=groups))

        # place statuses
        export_queryset(PlaceStatus.objects.filter(group__in=groups))

        # places
        export_queryset(Place.objects.filter(group__in=groups))

        # activity series
        export_queryset(ActivitySeries.objects.filter(place__group__in=groups))
        export_queryset(SeriesParticipantType.objects.filter(activity_series__place__group__in=groups))

        # feedback
        export_queryset(Feedback.objects.filter(about__place__group__in=groups))
        export_queryset(FeedbackNoShow.objects.filter(feedback__about__place__group__in=groups))
