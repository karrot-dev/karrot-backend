from io import BytesIO
from os.path import join
from tarfile import TarFile, TarInfo
from typing import List

import orjson
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser

from karrot.activities.models import ActivitySeries, Feedback
from karrot.groups.models import Group
from karrot.migrate.serializers import (
    ActivitySeriesMigrateSerializer,
    FeedbackMigrateSerializer,
    GroupMigrateOutSerializer,
    MigrateFileSerializer,
    PlaceMigrateSerializer,
    UserMigrateSerializer,
)
from karrot.places.models import Place


class FakeRequest:
    user = AnonymousUser()


def export_to_file(group_ids: List[int], output_filename: str):
    with TarFile.open(output_filename, "w|xz") as tarfile:
        groups = Group.objects.filter(id__in=group_ids)
        if len(groups) != len(group_ids):
            print("Not all groups found")
            return

        fake_request = FakeRequest()
        serializer_context = {"request": fake_request}

        def export_queryset(data_type, qs, serializer_class):
            contents = BytesIO()
            for item in qs.order_by("pk").iterator():
                item_data = serializer_class(item, context=serializer_context).data
                contents.write(orjson.dumps(item_data))
                contents.write(b"\n")
            contents.seek(0)
            json_info = TarInfo(f"{data_type}.json")
            json_info.size = contents.getbuffer().nbytes

            # before exporting the json export any files first
            # so when we import they are already there!
            for file in MigrateFileSerializer.exported_files:
                file_info = TarInfo(join("files", file.name))
                file_info.size = file.size
                tarfile.addfile(file_info, file)
            MigrateFileSerializer.exported_files = []

            tarfile.addfile(json_info, contents)

        # users
        # export them first as they are referred to in lots of other things
        export_queryset(
            "users",
            get_user_model().objects.filter(groupmembership__group__in=groups),
            UserMigrateSerializer,
        )

        # groups
        export_queryset(
            "groups",
            groups,
            GroupMigrateOutSerializer,
        )

        # places
        export_queryset(
            "places",
            Place.objects.filter(group__in=groups),
            PlaceMigrateSerializer,
        )

        # activity series
        export_queryset(
            "activity_series",
            ActivitySeries.objects.filter(place__group__in=groups),
            ActivitySeriesMigrateSerializer,
        )

        # feedback
        export_queryset(
            "feedback",
            Feedback.objects.filter(about__place__group__in=groups),
            FeedbackMigrateSerializer,
        )
