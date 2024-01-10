from collections import defaultdict
from os import makedirs
from os.path import dirname, join, splitext
from shutil import copyfileobj
from tarfile import TarFile
from tempfile import TemporaryDirectory

import orjson
from django.contrib.auth.hashers import make_password
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ForeignKey
from django.utils import timezone

from karrot.migrate.serializers import (
    MigrateFileSerializer,
    get_migrate_serializer_class,
)
from karrot.users.models import User


def create_anonymous_user():
    """Create anon deleted user that we can use for missing user foreign key

    It might be there are import records that refers to users that are not imported
    ... and for cases where that field is required, we can use this to set it to
    an anonymous user.
    """
    return User.objects.create(
        description="",
        email=None,
        is_active=False,
        is_staff=False,
        mail_verified=False,
        unverified_email=None,
        username=make_password(None),
        display_name="",
        address=None,
        latitude=None,
        longitude=None,
        mobile_number="",
        deleted_at=timezone.now(),
        deleted=True,
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
        anon_user = None

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
                if orig_id in mapping:
                    imported_id = mapping[orig_id]
                    data[field_name] = imported_id
                elif field.null:  # means allows null value
                    # the mapping is missing, but the field is not required
                    # likely means something like a referenced user that is not in the group anymore
                    print(
                        "Warning: missing id mapping for optional field",
                        model_class,
                        field_name,
                        orig_id,
                        "setting to null",
                    )
                    data[field_name] = None
                elif foreign_key_model_class is User:
                    # a required user field
                    nonlocal anon_user
                    if not anon_user:
                        anon_user = create_anonymous_user()
                    print(
                        "Warning: missing id mapping for required field",
                        model_class,
                        field_name,
                        orig_id,
                        "setting to anon user",
                    )
                    data[field_name] = anon_user.id
                else:
                    raise ValueError(
                        "missing id mapping for required field",
                        model_class,
                        field_name,
                        orig_id,
                    )

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
