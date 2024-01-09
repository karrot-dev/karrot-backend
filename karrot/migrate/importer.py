from collections import defaultdict
from os import makedirs
from os.path import dirname, join, splitext
from shutil import copyfileobj
from tarfile import TarFile
from tempfile import TemporaryDirectory

import orjson
from django.db import transaction

from karrot.migrate.serializers import (
    ActivitySeriesMigrateSerializer,
    GroupMigrateInSerializer,
    MigrateFileSerializer,
    PlaceMigrateSerializer,
    UserMigrateSerializer,
)


def import_from_file(input_filename: str):
    with transaction.atomic(), TemporaryDirectory() as tmpdir, TarFile.open(input_filename, "r|xz") as tarfile:
        MigrateFileSerializer.import_dir = tmpdir
        MigrateFileSerializer.imported_files = []

        id_mappings = defaultdict(dict)

        for member in tarfile:
            if member.name.startswith("files/"):
                # we copy all the files into our tmpdir first
                filename = member.name.removeprefix("files/")
                file = tarfile.extractfile(member)
                file_tmp_dest = join(tmpdir, filename)
                makedirs(dirname(file_tmp_dest), exist_ok=True)
                with open(file_tmp_dest, "wb") as f:
                    copyfileobj(file, f)
                MigrateFileSerializer.imported_files.append(filename)

            entry_type, ext = splitext(member.name)
            if ext == ".json":  # == "groups.json":
                for line in tarfile.extractfile(member).readlines():
                    json_data = orjson.loads(line)
                    # we don't import with original id, but we do keep a mapping, for later relations
                    original_id = json_data.pop("id")

                    # exclude null values, as this allows serializer fields with required=False to work
                    import_data = {k: json_data[k] for k in json_data.keys() if json_data[k] is not None}

                    id_mapping = id_mappings[entry_type]

                    # print("import_data", import_data)
                    serializer_class = {
                        "groups": GroupMigrateInSerializer,
                        "users": UserMigrateSerializer,
                        "places": PlaceMigrateSerializer,
                        "activity_series": ActivitySeriesMigrateSerializer,
                    }.get(entry_type, None)
                    if not serializer_class:
                        raise ValueError(f"missing serializer for type {entry_type}")

                    if entry_type == "places":
                        print("mapped group id from", import_data["group"])
                        import_data["group"] = id_mappings["groups"][import_data["group"]]
                        print("to", import_data["group"])

                    serializer = serializer_class(data=import_data)
                    serializer.is_valid(raise_exception=True)
                    entity = serializer.save()
                    print("added id mapping", entry_type, original_id, entity.id)
                    id_mapping[original_id] = entity.id

                    # if name == "groups":
                    #     s = GroupMigrateInSerializer(data=import_data)
                    #     s.is_valid(raise_exception=True)
                    #     # print("group memberships?", s._validated_data)
                    #     s.save()
                    # elif name == "users":
                    #     s = UserMigrateSerializer(data=import_data)
                    #     s.is_valid(raise_exception=True)
                    #     s.save()
                    # elif name == "places":
                    #     s = PlaceMigrateSerializer(data=import_data)
                    #     s.is_valid(raise_exception=True)
                    #     s.save()
                    # elif name == "activity_series":
                    #     s = ActivitySeriesMigrateSerializer(data=import_data)
                    #     s.is_valid(raise_exception=True)
                    #     s.save()

                    # TODO: how to read the files out...
                    # I guess could just keep the json around until everything is done?
                    # although I'm trying to make it incremental... in my current scenario files aren't always required
                    # but attachments do require a file.
                    # I could export it with the files first?
                    # let's see how that goes...
                    # yes, that's good, can maybe then move them into place?
                    # lets see... make food now!

    MigrateFileSerializer.import_dir = None
    MigrateFileSerializer.imported_files = []
