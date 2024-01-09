from collections import defaultdict
from os import makedirs
from os.path import dirname, join, splitext
from shutil import copyfileobj
from tarfile import TarFile
from tempfile import TemporaryDirectory

import orjson
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import Model

from karrot.activities.models import ActivitySeries, ActivityType
from karrot.groups.models import Group
from karrot.migrate.serializers import (
    ActivitySeriesMigrateSerializer,
    ActivityTypeMigrateSerializer,
    GroupImportSerializer,
    MigrateFileSerializer,
    PlaceMigrateSerializer,
    PlaceStatusMigrateSerializer,
    PlaceTypeMigrateSerializer,
    UserMigrateSerializer,
)
from karrot.places.models import Place, PlaceStatus, PlaceType
from karrot.users.models import User


def import_from_file(input_filename: str):
    with transaction.atomic(), TemporaryDirectory() as tmpdir, TarFile.open(input_filename, "r|xz") as tarfile:
        MigrateFileSerializer.imported_files = {}

        id_mappings = defaultdict(dict)

        def map_id(data: dict, field_name: str, map_model_class: type[Model]):
            if isinstance(data.get(field_name, None), int):
                data[field_name] = id_mappings[map_model_class][data[field_name]]

        for member in tarfile:
            if member.name.startswith("files/"):
                # we copy all the files into our tmpdir first
                filename = member.name.removeprefix("files/")
                file = tarfile.extractfile(member)
                file_tmp_dest = join(tmpdir, filename)
                makedirs(dirname(file_tmp_dest), exist_ok=True)
                with open(file_tmp_dest, "wb") as f:
                    copyfileobj(file, f)
                MigrateFileSerializer.imported_files[filename] = file_tmp_dest

            data_type, ext = splitext(member.name)
            if ext == ".json":  # == "groups.json":
                for line in tarfile.extractfile(member).readlines():
                    json_data = orjson.loads(line)

                    # we don't import with original id, but we do keep a mapping during the import
                    # so we can tie up related things
                    original_id = json_data.pop("id")

                    # exclude null values, as this allows serializer fields with required=False to work
                    import_data = {k: json_data[k] for k in json_data.keys() if json_data[k] is not None}

                    app_label, model_name = data_type.split(".", 2)
                    ct = ContentType.objects.get(app_label=app_label, model=model_name)
                    model_class = ct.model_class()

                    serializer_class = {
                        Group: GroupImportSerializer,
                        User: UserMigrateSerializer,
                        Place: PlaceMigrateSerializer,
                        ActivitySeries: ActivitySeriesMigrateSerializer,
                        ActivityType: ActivityTypeMigrateSerializer,
                        PlaceType: PlaceTypeMigrateSerializer,
                        PlaceStatus: PlaceStatusMigrateSerializer,
                    }.get(model_class, None)
                    if not serializer_class:
                        raise ValueError(f"missing serializer for type {data_type}")

                    # mapping from old id to new id
                    # assumes the things were exported in the correct order

                    map_id(import_data, "group", Group)
                    map_id(import_data, "place", Place)
                    map_id(import_data, "place_type", PlaceType)
                    map_id(import_data, "activity_type", ActivityType)
                    if model_class is Place:
                        # extra check, incase something else has a "status" field
                        map_id(import_data, "status", PlaceStatus)

                    print("importing data", import_data)
                    serializer = serializer_class(data=import_data)
                    serializer.is_valid(raise_exception=True)
                    entity = serializer.save()
                    # record our mapping
                    id_mappings[model_class][original_id] = entity.id
