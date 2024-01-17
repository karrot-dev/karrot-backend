import mimetypes
from os.path import getsize

from django.core.files.uploadedfile import UploadedFile
from django.db.models import Model
from rest_framework import serializers
from rest_framework.fields import ImageField

from karrot.groups.models import Group


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
    """Handles files during import/export

    Replace any FileField/ImageField/VersatileImageField with this to have
    the files handled correctly for export and import.

    During export it gives you the relative file path and keeps track of
    which files have been exported in "exported_files" class variable.

    "exported_files" is read elsewhere during the export to add them to
    the archive file.

    During import we expect "imported_files" gets pre-populated to map
    from the relative file path to a temp file that has been extracted
    from the archive already.

    We then pass a file field through, so it can get saved properly.
    """

    exported_files = []  # list of file field values that were exported
    imported_files = {}  # maps relative filename -> tmp file path

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


def get_migrate_serializer_class(model_class: type[Model]) -> type[serializers.ModelSerializer]:
    """Dynamically creates a serializer class for use for export/import

    It is a simple serializer just returning __all__ fields.
    It does not handle any kind of nested fields, you are expected to export all the related
    tables separately.

    It has special handling for image fields, to automatically use the MigrateFileSerializer.
    """

    # generic serializer with all fields
    class MigrateSerializer(serializers.ModelSerializer):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            for name in self.fields.keys():
                field = self.fields[name]
                if isinstance(field, ImageField):
                    # replace ImageFields with our special file migration serializer
                    self.fields[name] = MigrateFileSerializer(
                        required=field.required,
                        allow_null=field.allow_null,
                        context=field.context,
                    )

        class Meta:
            model = model_class
            fields = "__all__"

    return MigrateSerializer
