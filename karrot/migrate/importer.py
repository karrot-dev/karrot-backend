from collections import defaultdict
from os import makedirs
from os.path import dirname, join, splitext
from shutil import copyfileobj
from tarfile import TarFile
from tempfile import TemporaryDirectory

import orjson
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ForeignKey

from karrot.migrate.serializers import (
    MigrateFileSerializer,
    get_migrate_serializer_class,
)


def import_from_file(input_filename: str):
    """Imports from a tar.xz archive created using export_to_file

    The import is done inside a database transaction, so it's all or nothing.
    We don't preserve the original database ids, so they cannot clash with existing ids in the database you
    are importing into.

    For the duration of the import we keep a mapping of original_id -> imported_id so we can handle
    all the foreign key fields.
    """
    with transaction.atomic(), TemporaryDirectory() as tmpdir, TarFile.open(input_filename, "r|xz") as tarfile:
        MigrateFileSerializer.imported_files = {}

        id_mappings = defaultdict(dict)

        def update_foreign_key_ids(data: dict, field):
            """Finds the foreign key fields, and swaps the original id for the newly imported id

            Depends on the related object having been imported first.
            """
            if not isinstance(field, ForeignKey):
                return
            field_name = field.name
            foreign_key_model_class = field.remote_field.model
            if isinstance(data.get(field_name, None), int):
                mapping = id_mappings[foreign_key_model_class]
                orig_id = data[field_name]
                if orig_id not in mapping:
                    raise ValueError("missing id mapping for", model_class, field_name)
                imported_id = mapping[orig_id]
                data[field_name] = imported_id

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

                    # mapping from original ids to imported ids
                    # assumes the things were exported in the correct order
                    # such that the ids are already known by the time we need them
                    for model_field in model_class._meta.get_fields():
                        update_foreign_key_ids(import_data, model_field)

                    MigrateSerializer = get_migrate_serializer_class(model_class)
                    serializer = MigrateSerializer(data=import_data)
                    serializer.is_valid(raise_exception=True)
                    entity = serializer.save()

                    # record the imported id
                    id_mappings[model_class][original_id] = entity.id
