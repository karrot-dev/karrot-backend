from collections import defaultdict
from contextlib import contextmanager
from os import makedirs
from os.path import dirname, join, splitext
from shutil import copyfileobj
from tarfile import TarFile
from tempfile import NamedTemporaryFile, TemporaryDirectory
from typing import IO

import gnupg
import orjson
from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.db.models import ForeignKey

from karrot.activities.models import (
    Activity,
    ActivityParticipant,
    ActivitySeries,
    ActivityType,
    Feedback,
    FeedbackNoShow,
    ParticipantType,
    SeriesParticipantType,
)
from karrot.agreements.models import Agreement
from karrot.groups.models import Group, GroupMembership, Role, Trust
from karrot.migrate.migrate_utils import create_anonymous_user, disabled_signals
from karrot.migrate.serializers import (
    MigrateFileSerializer,
    get_migrate_serializer_class,
)
from karrot.offers.models import Offer, OfferImage
from karrot.places.models import Place, PlaceStatus, PlaceSubscription, PlaceType
from karrot.users.models import User

import_order = [
    Group,
    User,
    Role,
    GroupMembership,
    Trust,
    Agreement,
    PlaceType,
    PlaceStatus,
    Place,
    PlaceSubscription,
    ActivityType,
    ActivitySeries,
    SeriesParticipantType,
    Activity,
    ParticipantType,
    ActivityParticipant,
    Feedback,
    FeedbackNoShow,
    Offer,
    OfferImage,
]


@contextmanager
def decrypted_file(input_filename: str, password: str):
    with (
        TemporaryDirectory() as home,
        NamedTemporaryFile() as tmp,
    ):
        # use a tmp home to ensure we have clean environment
        gpg = gnupg.GPG(gnupghome=home)

        result = gpg.decrypt_file(
            input_filename,
            passphrase=password,
            output=tmp.name,
        )
        if not result.ok:
            raise RuntimeError(result.status)

        yield tmp


def import_from_file(input_filename: str, password: str = None):
    if input_filename.endswith(".gpg"):
        with decrypted_file(input_filename, password) as file:
            import_from_io(file)
    else:
        with open(input_filename, "rb") as file:
            import_from_io(file)


def import_from_io(io: IO):
    """Imports from a tar.xz archive created using export_to_file

    The import is done inside a database transaction, so it's all or nothing.
    We don't preserve the original database ids, so they cannot clash with existing ids in the database you
    are importing into.

    For the duration of the import we keep a mapping of original_id -> imported_id so we can handle
    all the foreign key fields.
    """
    with (
        disabled_signals(),
        transaction.atomic(),
        TemporaryDirectory() as tmpdir,
        TarFile.open(fileobj=io, mode="r|xz") as tarfile,
    ):
        MigrateFileSerializer.imported_files = {}

        id_mappings = defaultdict(dict)
        anon_users = {}  # original id -> anon_user

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
                    # we create an anon user for each original user id
                    # this is so unique constraints by user can still work
                    # e.g. ActivityParticipant objects
                    nonlocal anon_users
                    if orig_id not in anon_users:
                        anon_users[orig_id] = create_anonymous_user()
                    anon_user = anon_users[orig_id]
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

        data_entries = defaultdict(list)  # data_type -> List[json_data]

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
            if ext == ".json":
                for line in tarfile.extractfile(member).readlines():
                    json_data = orjson.loads(line)
                    data_entries[data_type].append(json_data)

        for model_class in import_order:
            ct = ContentType.objects.get_for_model(model_class)
            data_type = f"{ct.app_label}.{ct.model}"

            json_data_entries = data_entries.pop(data_type, [])

            for json_data in json_data_entries:
                # we don't import with original id, but we do keep a mapping during the import
                # so we can tie up related things
                original_id = json_data.pop("id")

                # exclude null values, as this allows serializer fields with required=False to work
                import_data = {k: json_data[k] for k in json_data.keys() if json_data[k] is not None}

                app_label, model_name = data_type.split(".", 2)
                ct = ContentType.objects.get(app_label=app_label, model=model_name)
                model_class = ct.model_class()

                skip_import = False

                if model_class is User:
                    existing_user = User.objects.filter(email=import_data["email"]).first()
                    if existing_user:
                        # if it's a user we're importing and they already exist, use that user
                        skip_import = True
                        id_mappings[model_class][original_id] = existing_user.id

                if not skip_import:
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

        if len(data_entries) > 0:
            raise ValueError("imported did not import all the data, failing entire import")
