import mimetypes
from os.path import getsize

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model
from rest_framework import serializers

from karrot.groups.models import Group
from karrot.users.models import User


class MigrationFile(UploadedFile):
    def __init__(self, file, name, content_type, size, charset=None, content_type_extra=None):
        super().__init__(file, name, content_type, size, charset, content_type_extra)

    def close(self):
        try:
            return self.file.close()
        except FileNotFoundError:
            # don't sweat it
            pass


class MigrateFileSerializer(serializers.Serializer):
    exported_files = []
    imported_files = {}

    def to_internal_value(self, filename):
        if not filename:
            return None
        file_path = MigrateFileSerializer.imported_files.get(filename, None)
        if not file_path:
            raise ValueError("missing file import", filename)
        content_type, _ = mimetypes.guess_type(filename)
        return MigrationFile(open(file_path, "rb"), filename, content_type, getsize(file_path))

    def to_representation(self, field_file):
        if not field_file:
            return None
        MigrateFileSerializer.exported_files.append(field_file)
        return field_file.name


class GroupMigrateSerializer(serializers.ModelSerializer):
    photo = MigrateFileSerializer(required=False)

    class Meta:
        model = Group
        fields = "__all__"


class UserMigrateSerializer(serializers.ModelSerializer):
    photo = MigrateFileSerializer(required=False)

    class Meta:
        model = get_user_model()
        fields = "__all__"


def get_migrate_serializer_class(model_class: type[Model]) -> type[serializers.ModelSerializer]:
    # special cases
    if model_class is Group:
        return GroupMigrateSerializer

    if model_class is User:
        return UserMigrateSerializer

    # generic serializer with all fields
    class MigrateSerializer(serializers.ModelSerializer):
        class Meta:
            model = model_class
            fields = "__all__"

    return MigrateSerializer
