import mimetypes
from os.path import getsize

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import UploadedFile
from rest_framework import serializers

from karrot.activities.models import ActivitySeries, ActivityType, Feedback
from karrot.activities.serializers import ParticipantTypeSerializer
from karrot.groups.models import Group, GroupMembership
from karrot.places.models import Place, PlaceStatus, PlaceType
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


class GroupMembershipExportSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()

    class Meta:
        model = GroupMembership
        fields = [
            "email",
            "roles",
            "notification_types",
        ]

    def get_email(self, membership):
        return membership.user.email


class GroupMembershipImportSerializer(serializers.ModelSerializer):
    email = serializers.EmailField()

    class Meta:
        model = GroupMembership
        fields = [
            "email",
            "roles",
            "notification_types",
        ]


class GroupExportSerializer(serializers.ModelSerializer):
    photo = MigrateFileSerializer(required=False)
    memberships = GroupMembershipExportSerializer(many=True, source="groupmembership_set")

    class Meta:
        model = Group
        fields = [
            "id",
            "name",
            "public_description",
            "application_questions",
            "address",
            "latitude",
            "longitude",
            "status",
            "theme",
            "photo",
            "memberships",
        ]


class GroupImportSerializer(GroupExportSerializer):
    memberships = GroupMembershipImportSerializer(many=True, source="groupmembership_set")

    class Meta:
        model = Group
        fields = GroupExportSerializer.Meta.fields

    def create(self, validated_data):
        memberships = validated_data.pop("groupmembership_set", None)

        group = super().create(validated_data)

        # create the nested memberships
        for membership in memberships:
            email = membership.pop("email")
            user = User.objects.get(email=email)
            group.groupmembership_set.create(user=user, **membership)

        return group


class FeedbackMigrateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Feedback
        fields = [
            "id",
            "weight",
            "comment",
            "about",
            "given_by",
            "created_at",
            "no_shows",
        ]


class PlaceMigrateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Place
        fields = [
            "id",
            "name",
            "description",
            "group",
            "address",
            "latitude",
            "longitude",
            "weeks_in_advance",
            "status",
            "archived_at",
            "is_archived",
            "place_type",
            "default_view",
        ]


class UserMigrateSerializer(serializers.ModelSerializer):
    photo = MigrateFileSerializer(required=False)

    class Meta:
        model = get_user_model()
        fields = [
            "id",
            "username",
            "display_name",
            "email",
            "mobile_number",
            "address",
            "latitude",
            "longitude",
            "description",
            "photo",
        ]


class ActivitySeriesMigrateSerializer(serializers.ModelSerializer):
    participant_types = ParticipantTypeSerializer(many=True)

    class Meta:
        model = ActivitySeries
        fields = [
            "id",
            "activity_type",
            "participant_types",
            "place",
            "rule",
            "start_date",
            "description",
            "duration",
        ]


class ActivityTypeMigrateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = "__all__"


class PlaceTypeMigrateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceType
        fields = "__all__"


class PlaceStatusMigrateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceStatus
        fields = "__all__"
