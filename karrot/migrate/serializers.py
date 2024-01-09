from django.contrib.auth import get_user_model
from rest_framework import serializers

from karrot.activities.models import ActivitySeries, Feedback
from karrot.activities.serializers import ParticipantTypeSerializer
from karrot.groups.models import Group, GroupMembership
from karrot.places.models import Place
from karrot.users.models import User


class MigrateFileSerializer(serializers.Serializer):
    exported_files = []
    import_dir = None
    imported_files = []

    def to_internal_value(self, filename):
        if not filename:
            return None
        if filename not in MigrateFileSerializer.imported_files:
            raise ValueError("missing file import", filename)
        print("WE HAVE THE IMPROT FILE!", filename)
        # what do we do now? give it a file? or a filepath?
        # return join(MigrateFileSerializer.import_dir, filename)
        return None
        # raise Exception("did not think about this yet")

    def to_representation(self, field_file):
        if not field_file:
            return None
        MigrateFileSerializer.exported_files.append(field_file)
        return field_file.name


class GroupMembershipMigrateOutSerializer(serializers.ModelSerializer):
    email = serializers.SerializerMethodField()
    # email = serializers.EmailField()

    class Meta:
        model = GroupMembership
        fields = [
            "email",
            "roles",
            "notification_types",
        ]

    def get_email(self, membership):
        return membership.user.email


class GroupMembershipMigrateInSerializer(serializers.ModelSerializer):
    # email = serializers.SerializerMethodField()
    email = serializers.EmailField()

    class Meta:
        model = GroupMembership
        fields = [
            "email",
            "roles",
            "notification_types",
        ]


class GroupMigrateOutSerializer(serializers.ModelSerializer):
    photo = MigrateFileSerializer(required=False)
    memberships = GroupMembershipMigrateOutSerializer(many=True, source="groupmembership_set")

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


class GroupMigrateInSerializer(GroupMigrateOutSerializer):
    memberships = GroupMembershipMigrateInSerializer(many=True, source="groupmembership_set")

    class Meta:
        model = Group
        fields = GroupMigrateOutSerializer.Meta.fields

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
