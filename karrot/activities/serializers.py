import uuid
from datetime import timedelta

import dateutil.rrule
from django.conf import settings
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.db.models import F
from django.db.models.functions import Coalesce, Lower
from django.forms import model_to_dict
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from icalendar import vCalAddress, vText
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import CharField, DateTimeField, Field
from rest_framework.serializers import Serializer
from rest_framework.validators import UniqueTogetherValidator
from rest_framework_csv.renderers import CSVRenderer
from versatileimagefield.serializers import VersatileImageFieldSerializer

from karrot.activities import stats
from karrot.activities.models import (
    Activity,
    ActivityParticipant,
    ActivityType,
    FeedbackNoShow,
    ParticipantType,
    SeriesParticipantType,
    default_duration,
)
from karrot.activities.models import (
    Activity as ActivityModel,
)
from karrot.activities.models import (
    ActivitySeries as ActivitySeriesModel,
)
from karrot.activities.models import (
    Feedback as FeedbackModel,
)
from karrot.activities.tasks import notify_participant_removals
from karrot.base.base_models import CustomDateTimeTZRange, GenRandomUUID, Tstzrange
from karrot.history.models import History, HistoryTypus
from karrot.places.serializers import PublicPlaceSerializer
from karrot.utils.date_utils import csv_datetime
from karrot.utils.misc import find_changed, is_prefetched


class FeedbackNoShowSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackNoShow
        fields = ["user"]


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackModel
        fields = [
            "id",
            "weight",
            "comment",
            "about",
            "given_by",
            "created_at",
            "is_editable",
            "no_shows",
        ]
        read_only_fields = ["given_by", "created_at"]
        extra_kwargs = {"given_by": {"default": serializers.CurrentUserDefault()}}
        validators = [
            UniqueTogetherValidator(queryset=FeedbackModel.objects.all(), fields=FeedbackModel._meta.unique_together[0])
        ]

    is_editable = serializers.SerializerMethodField()
    no_shows = FeedbackNoShowSerializer(many=True, required=False)

    def create(self, validated_data):
        no_shows = validated_data.pop("no_shows", None)
        feedback = super().create(validated_data)
        if no_shows:
            for no_show in no_shows:
                feedback.no_shows.create(**no_show)
        feedback.about.place.group.refresh_active_status()
        return feedback

    def update(self, feedback, validated_data):
        no_shows = validated_data.pop("no_shows", None)
        feedback = super().update(feedback, validated_data)
        if no_shows is not None:
            existing_no_shows = list(feedback.no_shows.all())
            for no_show in no_shows:
                existing_no_show = None
                for entry in existing_no_shows:
                    if entry.user_id == no_show["user"].id:
                        existing_no_show = entry

                if existing_no_show:
                    # we don't have anything to update about it, but if we had more attrs on it
                    # this would be where we update it
                    existing_no_shows.remove(existing_no_show)
                else:
                    feedback.no_shows.create(**no_show)

            # remove anything leftover
            for entry in existing_no_shows:
                entry.delete()

        feedback.about.place.group.refresh_active_status()
        return feedback

    def get_is_editable(self, feedback) -> bool:
        return feedback.about.is_recent() and feedback.given_by_id == self.context["request"].user.id

    def validate_about(self, about):
        user = self.context["request"].user
        group = about.place.group
        if not group.is_member(user):
            raise serializers.ValidationError("You are not member of the place's group.")
        if about.is_upcoming():
            raise serializers.ValidationError("The activity is not done yet")
        if not about.is_participant(user):
            raise serializers.ValidationError("You aren't assigned to the activity.")
        if not about.is_recent():
            raise serializers.ValidationError(
                f"You can't give feedback for activities more than {settings.FEEDBACK_POSSIBLE_DAYS} days ago."
            )
        return about

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity = data.get("about", get_instance_attr("about"))
        activity_type = activity.activity_type

        comment = data.get("comment", get_instance_attr("comment"))
        weight = data.get("weight", get_instance_attr("weight"))

        if not activity_type.has_feedback:
            raise serializers.ValidationError(f"You cannot give feedback to an activity of type {activity_type.name}.")

        if weight is not None and not activity_type.has_feedback_weight:
            raise serializers.ValidationError(
                f"You cannot give weight feedback to an activity of type {activity_type.name}."
            )

        if (comment is None or comment == "") and weight is None:
            raise serializers.ValidationError("Both comment and weight cannot be blank.")

        no_shows = data.get("no_shows", None)
        if no_shows:
            # confusingly "participants" are the user entries not ActivityParticipant ones
            user_ids = activity.participants.values_list("id", flat=True)
            for no_show in no_shows:
                if no_show["user"].id not in user_ids:
                    raise serializers.ValidationError("user is not participant")

        data["given_by"] = self.context["request"].user
        return data


class FeedbackExportSerializer(FeedbackSerializer):
    class Meta:
        model = FeedbackModel
        fields = [
            "id",
            "about_place",
            "given_by",
            "about",
            "created_at",
            "about_date",
            "weight",
            "comment",
        ]

    about_date = serializers.SerializerMethodField()
    about_place = serializers.SerializerMethodField()
    created_at = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_about_date(self, feedback):
        activity = feedback.about
        group = activity.place.group

        return csv_datetime(activity.date.start.astimezone(group.timezone))

    @extend_schema_field(OpenApiTypes.INT)
    def get_about_place(self, feedback):
        return feedback.about.place_id

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_created_at(self, feedback):
        activity = feedback.about
        group = activity.place.group

        return csv_datetime(feedback.created_at.astimezone(group.timezone))


class FeedbackExportRenderer(CSVRenderer):
    header = FeedbackExportSerializer.Meta.fields
    labels = {
        "about_place": "place_id",
        "about": "activity_id",
        "given_by": "user_id",
        "about_date": "date",
    }


class ActivityTypeSerializer(serializers.ModelSerializer):
    is_archived = serializers.BooleanField(default=False)
    updated_message = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = ActivityType
        fields = [
            "id",
            "name",
            "name_is_translatable",
            "description",
            "colour",
            "icon",
            "has_feedback",
            "has_feedback_weight",
            "feedback_icon",
            "archived_at",
            "is_archived",
            "group",
            "created_at",
            "updated_at",
            "updated_message",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "archived_at",
        ]

    def validate_group(self, group):
        if not group.is_member(self.context["request"].user):
            raise PermissionDenied("You are not a member of this group.")
        if not group.is_editor(self.context["request"].user):
            raise PermissionDenied("You need to be a group editor")
        return group

    def save(self, **kwargs):
        if not self.instance:
            return super().save(**kwargs)

        updated_message = self.validated_data.pop("updated_message", None)

        if "is_archived" in self.validated_data:
            is_archived = self.validated_data.pop("is_archived")
            archived_at = timezone.now() if is_archived else None
            self.initial_data["archived_at"] = self.validated_data["archived_at"] = archived_at

        activity_type = self.instance
        changed_data = find_changed(activity_type, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        before_data = ActivityTypeHistorySerializer(activity_type).data
        activity_type = super().save(**kwargs)
        after_data = ActivityTypeHistorySerializer(activity_type).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.ACTIVITY_TYPE_MODIFY,
                group=activity_type.group,
                users=[self.context["request"].user],
                payload={k: self.initial_data.get(k) for k in changed_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )
        return activity_type

    def create(self, validated_data):
        if "is_archived" in validated_data:
            # can't create something in an archived state
            validated_data.pop("is_archived")
        activity_type = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.ACTIVITY_TYPE_CREATE,
            group=activity_type.group,
            users=[self.context["request"].user],
            payload=self.initial_data,
            after=ActivityTypeHistorySerializer(activity_type).data,
        )
        return activity_type


class ActivityTypeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = "__all__"


class DateTimeFieldWithTimezone(DateTimeField):
    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if value is None:
            return None
        if hasattr(instance, "timezone"):
            return value.astimezone(instance.timezone)
        return value

    def enforce_timezone(self, value):
        if value is None:
            return None
        if timezone.is_aware(value):
            return value
        return super().enforce_timezone(value)


class DateTimeRangeField(serializers.ListField):
    child = DateTimeFieldWithTimezone()

    default_error_messages = {
        "list": _("Must be a list"),
        "length": _("Must be a list with one or two values"),
        "required": _("Must pass start value"),
    }

    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if hasattr(instance, "timezone"):
            return value.astimezone(instance.timezone)
        return value

    def to_representation(self, value):
        return [
            self.child.to_representation(value.lower),
            self.child.to_representation(value.upper),
        ]

    def to_internal_value(self, data):
        if not isinstance(data, list):
            self.fail("list")
        if not 0 < len(data) <= 2:
            self.fail("length")
        lower = data[0]
        upper = data[1] if len(data) > 1 else None
        lower = self.child.to_internal_value(lower) if lower else None
        upper = self.child.to_internal_value(upper) if upper else None
        if not lower:
            self.fail("required")
        upper = lower + timedelta(minutes=30) if not upper else upper
        return CustomDateTimeTZRange(lower, upper)


class ActivityParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityParticipant
        fields = [
            "user",
            "participant_type",
            "created_at",
        ]
        read_only_fields = [
            "user",
            "participant_type",
            "created_at",
        ]


class ParticipantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParticipantType
        fields = [
            "id",
            "description",
            "max_participants",
            "series_participant_type",
            "role",
            "_removed",
        ]

    id = serializers.IntegerField(required=False)
    _removed = serializers.BooleanField(required=False)


class ActivityHistorySerializer(serializers.ModelSerializer):
    participant_types = ParticipantTypeSerializer(many=True)

    class Meta:
        model = ActivityModel
        fields = "__all__"


class SeriesParticipantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeriesParticipantType
        fields = [
            "id",
            "description",
            "max_participants",
            "role",
            "_removed",
        ]

    id = serializers.IntegerField(required=False)
    _removed = serializers.BooleanField(required=False)


class PublicActivitySerializer(serializers.ModelSerializer):
    banner_image_urls = VersatileImageFieldSerializer(sizes="activity_banner_image", source="banner_image")
    series_banner_image_urls = VersatileImageFieldSerializer(
        sizes="activity_banner_image",
        source="series.banner_image",
        read_only=True,
    )
    place = PublicPlaceSerializer()
    activity_type = ActivityTypeSerializer()
    date = DateTimeRangeField()

    class Meta:
        model = ActivityModel
        fields = [
            "public_id",
            "activity_type",
            "date",
            "place",
            "description",
            "is_disabled",
            "has_duration",
            "is_done",
            "is_public",
            "banner_image_urls",
            "series_banner_image_urls",
        ]
        read_only_fields = fields


class ActivitySerializer(serializers.ModelSerializer):
    banner_image = VersatileImageFieldSerializer(
        sizes="activity_banner_image", required=False, allow_null=True, write_only=True
    )
    banner_image_urls = VersatileImageFieldSerializer(
        sizes="activity_banner_image", source="banner_image", read_only=True
    )
    series_banner_image_urls = VersatileImageFieldSerializer(
        sizes="activity_banner_image", source="series.banner_image", read_only=True
    )

    class Meta:
        model = ActivityModel
        fields = [
            "id",
            "activity_type",
            "date",
            "series",
            "place",
            "participant_types",
            "participants",
            "description",
            "feedback_due",
            "feedback_given_by",
            "feedback_dismissed_by",
            "feedback",
            "is_disabled",
            "has_duration",
            "is_done",
            "is_public",
            "public_id",
            "banner_image",
            "banner_image_urls",
            "series_banner_image_urls",
        ]
        read_only_fields = [
            "id",
            "series",
            "is_done",
            "banner_image_urls",
            "series_banner_image_urls",
            "public_id",
        ]

    participants = ActivityParticipantSerializer(
        read_only=True,
        source="activityparticipant_set",
        many=True,
    )
    participant_types = ParticipantTypeSerializer(many=True)

    feedback_dismissed_by = serializers.SerializerMethodField()
    feedback_given_by = serializers.SerializerMethodField()
    feedback_due = DateTimeFieldWithTimezone(read_only=True, allow_null=True)

    feedback = serializers.SerializerMethodField()

    date = DateTimeRangeField()

    @staticmethod
    def get_feedback_given_by(activity) -> list[int] | None:
        # assume we only need it if we've prefetched it
        if is_prefetched(activity, "feedback_set"):
            return [f.given_by_id for f in activity.feedback_set.all()]
        return None

    @staticmethod
    def get_feedback_dismissed_by(activity) -> list[int] | None:
        # ensure we use prefetched data
        return [c.user_id for c in activity.activityparticipant_set.all() if c.feedback_dismissed]

    def get_feedback(self, activity) -> list | None:
        # assume we only need it if we've prefetched it
        if is_prefetched(activity, "feedback_set"):
            return FeedbackSerializer(activity.feedback_set.all(), many=True, context=self.context).data
        return None

    def create(self, validated_data):
        participant_types_data = validated_data.pop("participant_types")
        if "is_public" in validated_data and validated_data["is_public"]:
            validated_data["public_id"] = uuid.uuid4()
        activity = super().create({**validated_data, "last_changed_by": self.context["request"].user})
        for participant_type_data in participant_types_data:
            # creating the nested data
            activity.participant_types.create(**participant_type_data)

        History.objects.create(
            typus=HistoryTypus.ACTIVITY_CREATE,
            group=activity.place.group,
            place=activity.place,
            activity=activity,
            users=[self.context["request"].user],
            payload={
                # cannot serialize the UploadedFile data...
                k: self.initial_data[k]
                for k in self.initial_data.keys()
                if not isinstance(self.initial_data[k], UploadedFile)
            },
            after=ActivityHistorySerializer(activity).data,
        )
        activity.place.group.refresh_active_status()
        return activity

    def validate_activity_type(self, activity_type):
        if activity_type.is_archived:
            raise serializers.ValidationError("You can only create activities for active types")
        return activity_type

    def validate_place(self, place):
        if not place.group.is_editor(self.context["request"].user):
            if not place.group.is_member(self.context["request"].user):
                raise PermissionDenied("You are not member of the place's group.")
            raise PermissionDenied("You need to be a group editor")
        return place

    def validate_date(self, date):
        if not date.start > timezone.now() + timedelta(minutes=10):
            raise serializers.ValidationError("The date should be in the future.")
        duration = date.end - date.start
        if duration < timedelta(seconds=1):
            raise serializers.ValidationError("Duration must be at least one second.")
        return date

    def validate_participant_types(self, participant_types):
        for participant_type in participant_types:
            series_participant_type = participant_type.get("series_participant_type", None)
            if series_participant_type:
                if not self.instance:
                    # invalid to specify this, as these are only created by a karrot task, not by API
                    raise serializers.ValidationError("Cannot specify series_participant_type for new activity.")
                if series_participant_type.activity_series_id != self.instance.series_id:
                    raise serializers.ValidationError("Wrong series.")
        return participant_types

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity_type = data.get("activity_type", get_instance_attr("activity_type"))
        place = data.get("place", get_instance_attr("place"))

        if activity_type and place and activity_type.group_id != place.group_id:
            raise serializers.ValidationError("ActivityType is not for this group.")

        return data


class ActivityUpdateSerializer(ActivitySerializer):
    class Meta:
        model = ActivityModel
        fields = ActivitySerializer.Meta.fields + ["updated_message"]
        read_only_fields = ActivitySerializer.Meta.read_only_fields + ["place"]

    date = DateTimeRangeField()
    updated_message = serializers.CharField(write_only=True, required=False)

    @transaction.atomic()
    def update(self, activity, validated_data):
        # this is not part of the activity data itself, so pop it out...
        updated_message = validated_data.pop("updated_message", None)
        validated_data = find_changed(activity, validated_data)
        skip_update = len(validated_data.keys()) == 0
        if skip_update:
            return activity

        before_data = ActivityHistorySerializer(activity).data

        removed_users = []

        participant_types = validated_data.get("participant_types", None)
        if participant_types:
            for entry in participant_types:
                pk = entry.pop("id", None)
                if pk:
                    # existing participant type
                    participant_type = ParticipantType.objects.get(pk=pk)
                    if entry.get("_removed", False):
                        # existing participant type being deleted
                        participants = activity.activityparticipant_set.filter(participant_type=participant_type)

                        for participant in participants:
                            removed_users.append(participant.user)

                        participants.delete()
                        participant_type.delete()
                    else:
                        # existing participant type being edited
                        role = entry.get("role", None)
                        if role and role != participant_type.role:
                            # find all the participants who are missing the new role, and remove them...
                            users_with_new_role = activity.place.group.members.filter(
                                groupmembership__roles__contains=[role]
                            )
                            participants = activity.activityparticipant_set.filter(
                                participant_type=participant_type
                            ).exclude(user__in=users_with_new_role)
                            for participant in participants:
                                removed_users.append(participant.user)

                            participants.delete()

                        # update the rest of the fields
                        ParticipantType.objects.filter(pk=pk).update(**entry)
                else:
                    # new participant type \o/
                    ParticipantType.objects.create(activity=activity, **entry)

        update_data = validated_data.copy()

        if "is_public" in update_data and update_data["is_public"] and not activity.public_id:
            # create public id
            update_data["public_id"] = uuid.uuid4()

        if "banner_image" in validated_data:
            activity.delete_banner_image()

        update_data.pop("participant_types", None)
        update_data["last_changed_by"] = self.context["request"].user
        activity = super().update(activity, update_data)

        validated_data.pop("banner_image", None)  # can't store this in history, so remove it

        after_data = ActivityHistorySerializer(activity).data

        history = None

        if before_data != after_data:
            typus_list = []
            if "is_disabled" in validated_data:
                if validated_data["is_disabled"]:
                    typus_list.append(HistoryTypus.ACTIVITY_DISABLE)
                    stats.activity_disabled(activity)
                else:
                    typus_list.append(HistoryTypus.ACTIVITY_ENABLE)
                    stats.activity_enabled(activity)

            if len(set(validated_data.keys()).difference(["is_disabled"])) > 0:
                typus_list.append(HistoryTypus.ACTIVITY_MODIFY)

            for typus in typus_list:
                created_history = History.objects.create(
                    typus=typus,
                    group=activity.place.group,
                    place=activity.place,
                    activity=activity,
                    users=[self.context["request"].user],
                    payload={k: self.initial_data.get(k) for k in validated_data.keys()},
                    before=before_data,
                    after=after_data,
                    message=updated_message,
                )
                if typus is HistoryTypus.ACTIVITY_MODIFY:
                    history = created_history

        if len(removed_users) > 0:
            notify_participant_removals(
                activity_type_id=activity.activity_type.id,
                place_id=activity.place.id,
                activities_data=[model_to_dict(activity)],
                participants=[
                    {
                        "user": user.id,
                        "activity": activity.id,
                    }
                    for user in removed_users
                ],
                message=updated_message,
                removed_by_id=self.context["request"].user.id,
                history_id=history.id if history else None,
            )

        activity.place.group.refresh_active_status()

        return activity

    def validate_date(self, date):
        if self.instance.series is not None and abs((self.instance.date.start - date.start).total_seconds()) > 1:
            raise serializers.ValidationError("You can't move activities that are part of a series.")
        return super().validate_date(date)

    def validate_has_duration(self, has_duration):
        if self.instance.series is not None and has_duration != self.instance.has_duration:
            raise serializers.ValidationError("You cannot modify the duration of activities that are part of a series")
        return has_duration


class ActivityUpdateCheckSerializer(Serializer):
    # request fields
    participant_types = ParticipantTypeSerializer(many=True, write_only=True, required=False)

    # response fields
    users = serializers.ListSerializer(read_only=True, child=serializers.IntegerField())

    def update(self, activity, validated_data):
        will_remove_user_ids = set()

        participant_types = validated_data.get("participant_types", None)
        if participant_types:
            for entry in participant_types:
                pk = entry.pop("id", None)
                if pk:
                    # existing participant type
                    participant_type = ParticipantType.objects.get(pk=pk)
                    if entry.get("_removed", False):
                        # existing participant type would be deleted
                        participants = activity.activityparticipant_set.filter(participant_type=participant_type)
                        for participant in participants:
                            will_remove_user_ids.add(participant.user.id)
                    else:
                        # existing participant type being edited
                        role = entry.get("role", None)
                        if role and role != participant_type.role:
                            # find all the participants who are missing the new role
                            users_with_new_role = activity.place.group.members.filter(
                                groupmembership__roles__contains=[role]
                            )
                            participants = activity.activityparticipant_set.filter(
                                participant_type=participant_type
                            ).exclude(user__in=users_with_new_role)
                            for participant in participants:
                                will_remove_user_ids.add(participant.user.id)

        return {
            "users": will_remove_user_ids,
        }

    def create(self, validated_data):
        pass


class ActivityICSSerializer(serializers.ModelSerializer):
    """serializes an activity to the ICS format, in conjunction with the ICSEventRenderer.

    details of the allowed fields:
    https://www.kanzaki.com/docs/ical/vevent.html"""

    class Meta:
        model = ActivityModel
        fields = [
            "uid",
            "dtstamp",
            "summary",
            "description",
            "dtstart",
            "dtend",
            "transp",
            "categories",
            "location",
            "geo",
            "attendee",
            "status",
        ]

    # date of generation of the ICS representation of the event
    dtstamp = serializers.SerializerMethodField()
    # unique id, of the form uid@domain.com
    uid = serializers.SerializerMethodField()
    # status, one of "CONFIRMED", "TENTATIVE" or "CANCELLED"
    status = serializers.SerializerMethodField()

    # title (short description)
    summary = serializers.SerializerMethodField()
    # longer description
    description = CharField()

    # start date
    dtstart = DateTimeField(source="date.start", format=None)
    # end date
    dtend = DateTimeField(source="date.end", format=None)
    # opaque (busy)
    transp = serializers.SerializerMethodField()
    # comma-separated list of categories this activity is part of
    categories = serializers.SerializerMethodField()

    # where this activity happens (text description)
    location = serializers.SerializerMethodField()
    # latitude and longitude of the location (such as "37.386013;-122.082932")
    geo = serializers.SerializerMethodField()

    # participants' names and email addresses
    attendee = serializers.SerializerMethodField()

    def get_dtstamp(self, activity):
        return timezone.now()

    def get_uid(self, activity):
        request = self.context.get("request")
        domain = "karrot"
        if request and request.headers.get("host"):
            domain = request.headers.get("host")
        return f"activity_{activity.id}@{domain}"

    def get_status(self, activity):
        return "CANCELLED" if activity.is_disabled else "CONFIRMED"

    def get_summary(self, activity):
        return f"{activity.activity_type.name}: {activity.place.name}"

    def get_transp(self, activity):
        return "OPAQUE"

    def get_categories(self, activity):
        return [activity.activity_type.name]

    def get_location(self, activity):
        return activity.place.name

    def get_geo(self, activity):
        place = activity.place
        return (place.latitude, place.longitude) if place.latitude is not None else None

    def get_attendee(self, activity):
        attendees = []
        for attendee in activity.participants.all():
            address = vCalAddress(attendee.email)
            address.params["cn"] = vText(attendee.get_full_name())
            address.params["role"] = vText("REQ-PARTICIPANT")
            address.params["partstat"] = vText("ACCEPTED")
            attendees.append(address)
        return attendees


class PublicActivityICSSerializer(ActivityICSSerializer):
    def get_uid(self, activity):
        request = self.context.get("request")
        domain = "karrot"
        if request and request.headers.get("host"):
            domain = request.headers.get("host")
        return f"activity_{activity.public_id}@{domain}"

    def get_attendee(self, activity):
        return []


class ActivityJoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = [
            "participant_type",
        ]

    participant_type = serializers.IntegerField(write_only=True, default=None)

    def update(self, activity, validated_data):
        user = self.context["request"].user
        place = activity.place
        group = place.group

        pt_id = validated_data.get("participant_type", None)
        if pt_id:
            participant_type = activity.participant_types.get(id=pt_id)
        else:
            # if not supplied, and the activity has only 1, use that one
            if activity.participant_types.count() > 1:
                raise PermissionDenied("Must supply participant_type")
            participant_type = activity.participant_types.first()

        # check the user has the role
        if not group.is_member_with_role(user, participant_type.role):
            raise PermissionDenied("You do not have the required role.")

        # check there is space available
        if participant_type.is_full():
            raise PermissionDenied("Activity is already full.")

        activity.add_participant(user, participant_type)

        stats.activity_joined(activity)

        History.objects.create(
            typus=HistoryTypus.ACTIVITY_JOIN,
            group=group,
            place=place,
            activity=activity,
            users=[
                user,
            ],
            payload=ActivitySerializer(instance=activity).data,
        )
        group.refresh_active_status()
        return activity


class ActivityLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = []

    def update(self, activity, validated_data):
        user = self.context["request"].user
        activity.remove_participant(user)

        stats.activity_left(activity)

        History.objects.create(
            typus=HistoryTypus.ACTIVITY_LEAVE,
            group=activity.place.group,
            place=activity.place,
            activity=activity,
            users=[user],
            payload=ActivitySerializer(instance=activity).data,
        )
        activity.place.group.refresh_active_status()
        return activity


class ActivityDismissFeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = []

    def update(self, activity, validated_data):
        user = self.context["request"].user
        activity.dismiss_feedback(user)

        stats.feedback_dismissed(activity)

        activity.place.group.refresh_active_status()
        return activity


@extend_schema_field(OpenApiTypes.INT)
class DurationInSecondsField(Field):
    default_error_messages = {}

    def to_internal_value(self, value):
        return timedelta(seconds=value)

    def to_representation(self, value):
        return value.seconds


class ActivitySeriesHistorySerializer(serializers.ModelSerializer):
    participant_types = SeriesParticipantTypeSerializer(many=True)

    class Meta:
        model = ActivitySeriesModel
        fields = "__all__"


class ActivitySeriesSerializer(serializers.ModelSerializer):
    banner_image = VersatileImageFieldSerializer(
        sizes="activity_banner_image", required=False, allow_null=True, write_only=True
    )
    banner_image_urls = VersatileImageFieldSerializer(
        sizes="activity_banner_image", source="banner_image", read_only=True
    )

    class Meta:
        model = ActivitySeriesModel
        fields = [
            "id",
            "activity_type",
            "participant_types",
            "place",
            "rule",
            "start_date",
            "description",
            "dates_preview",
            "duration",
            "is_public",
            "banner_image",
            "banner_image_urls",
        ]
        read_only_fields = [
            "id",
        ]

    start_date = DateTimeFieldWithTimezone()
    dates_preview = serializers.ListField(
        child=DateTimeFieldWithTimezone(),
        read_only=True,
        source="dates",
    )

    participant_types = SeriesParticipantTypeSerializer(many=True)

    duration = DurationInSecondsField(required=False, allow_null=True)

    @transaction.atomic()
    def create(self, validated_data):
        participant_types_data = validated_data.pop("participant_types")
        series = super().create({**validated_data, "last_changed_by": self.context["request"].user})
        for participant_type_data in participant_types_data:
            # creating the nested data
            series.participant_types.create(**participant_type_data)
        series.update_activities()

        History.objects.create(
            typus=HistoryTypus.SERIES_CREATE,
            group=series.place.group,
            place=series.place,
            series=series,
            users=[self.context["request"].user],
            payload={
                # cannot serialize the UploadedFile data...
                k: self.initial_data[k]
                for k in self.initial_data.keys()
                if not isinstance(self.initial_data[k], UploadedFile)
            },
            after=ActivitySeriesHistorySerializer(series).data,
        )
        series.place.group.refresh_active_status()
        return series

    def validate_activity_type(self, activity_type):
        if activity_type.is_archived:
            raise serializers.ValidationError("You can only create series for active types")
        return activity_type

    def validate_place(self, place):
        if not place.group.is_editor(self.context["request"].user):
            raise PermissionDenied("You need to be a group editor")
        if not place.group.is_member(self.context["request"].user):
            raise serializers.ValidationError("You are not member of the place's group.")
        return place

    def validate_start_date(self, date):
        date = date.replace(second=0, microsecond=0)
        return date

    def validate_rule(self, rule_string):
        try:
            rrule = dateutil.rrule.rrulestr(rule_string)
        except ValueError as exc:
            raise serializers.ValidationError("Invalid recurrence rule.") from exc
        if not isinstance(rrule, dateutil.rrule.rrule):
            raise serializers.ValidationError("Only single recurrence rules are allowed.")
        return rule_string

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity_type = data.get("activity_type", get_instance_attr("activity_type"))
        place = data.get("place", get_instance_attr("place"))

        if activity_type and place and activity_type.group_id != place.group_id:
            raise serializers.ValidationError("ActivityType is not for this group.")

        return data


class ActivitySeriesUpdateSerializer(ActivitySeriesSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = ActivitySeriesSerializer.Meta.fields + ["updated_message"]
        read_only_fields = ActivitySeriesSerializer.Meta.read_only_fields + ["place"]

    duration = DurationInSecondsField(required=False, allow_null=True)
    updated_message = serializers.CharField(write_only=True, required=False)

    @transaction.atomic()
    def update(self, series, validated_data):
        old = series.old() if series else None

        # this is not part of the series data itself, so pop it out...
        updated_message = validated_data.pop("updated_message", None)
        validated_data = find_changed(series, validated_data)
        skip_update = len(validated_data.keys()) == 0
        if skip_update:
            return series

        before_data = ActivitySeriesHistorySerializer(series).data

        removed = []  # array of {'user': <User>, 'activity': <Activity> } objects

        def add_removed(activity, user):
            for entry in removed:
                if entry["user"].id == user.id and entry["activity"].id == activity.id:
                    return
            removed.append({"user": user, "activity": activity})

        description = validated_data.get("description", None)
        duration = validated_data.get("duration", None)
        is_public = validated_data.get("is_public", None)
        participant_types = validated_data.get("participant_types", None)

        description_changed = "description" in validated_data and series.description != description
        duration_changed = "duration" in validated_data and series.duration != duration
        is_public_changed = "is_public" in validated_data and series.is_public != is_public
        if description_changed or duration_changed or participant_types or is_public_changed:
            activities = series.activities.upcoming()

            if description_changed:
                # this update is filtered incase some of the descriptions were individually modified
                activities.filter(description=series.description).update(description=description)

            if duration_changed:
                activities.update(
                    has_duration=duration is not None,
                    date=Tstzrange(Lower(F("date")), Lower(F("date")) + (duration or default_duration)),
                )

            if is_public_changed:
                if is_public:
                    activities.update(
                        is_public=True,
                        # ensures we set a public id if not already set
                        public_id=Coalesce(F("public_id"), GenRandomUUID()),
                    )
                else:
                    activities.update(is_public=False)

            if participant_types:
                for entry in participant_types:
                    pk = entry.pop("id", None)
                    if pk:
                        # existing series participant type
                        series_participant_type = SeriesParticipantType.objects.get(pk=pk)
                        if entry.get("_removed", False):
                            # existing series participant type being deleted
                            participants = ActivityParticipant.objects.filter(
                                activity__in=activities,
                                participant_type__series_participant_type=series_participant_type,
                            )
                            for participant in participants:
                                add_removed(participant.activity, participant.user)
                            participants.delete()
                            ParticipantType.objects.filter(
                                series_participant_type=series_participant_type,
                                activity__in=activities,
                            ).delete()
                            series_participant_type.delete()
                        else:
                            # existing series participant type being edited
                            old_description = series_participant_type.description
                            description = entry.get("description", None)
                            description_changed = "description" in entry and description != old_description

                            old_max_participants = series_participant_type.max_participants
                            max_participants = entry.get("max_participants", None)
                            max_participants_changed = (
                                "max_participants" in entry and max_participants != old_max_participants
                            )

                            old_role = series_participant_type.role
                            role = entry.get("role", None)
                            role_changed = "role" in entry and role != old_role

                            if description_changed or max_participants_changed or role_changed:
                                # now we go through all the related participant types for the individual activities
                                for participant_type in ParticipantType.objects.filter(
                                    series_participant_type_id=pk,
                                    activity__in=activities,
                                ):
                                    if description_changed and participant_type.description == old_description:
                                        participant_type.description = description
                                    if (
                                        max_participants_changed
                                        and participant_type.max_participants == old_max_participants
                                    ):
                                        participant_type.max_participants = max_participants
                                    if role_changed and participant_type.role == old_role:
                                        participant_type.role = role
                                        # find all the participants who are missing the new role, and remove them...
                                        users_with_new_role = series.place.group.members.filter(
                                            groupmembership__roles__contains=[role]
                                        )
                                        participants = ActivityParticipant.objects.filter(
                                            participant_type=participant_type,
                                            activity__in=activities,
                                        ).exclude(user__in=users_with_new_role)
                                        for participant in participants:
                                            add_removed(participant.activity, participant.user)
                                        participants.delete()
                                    participant_type.save()

                            # update the rest of the stuff
                            SeriesParticipantType.objects.filter(pk=pk).update(**entry)
                    else:
                        # new series participant type \o/
                        series_participant_type = SeriesParticipantType.objects.create(activity_series=series, **entry)
                        for activity in activities:
                            # propagate it to all the activities
                            ParticipantType.objects.create(
                                activity=activity,
                                series_participant_type=series_participant_type,
                                **entry,
                            )

        if "banner_image" in validated_data:
            series.delete_banner_image()

        update_data = validated_data.copy()
        update_data.pop("participant_types", None)
        update_data["last_changed_by"] = self.context["request"].user
        series = super().update(series, update_data)

        validated_data.pop("banner_image", None)  # can't store this in history, so remove it

        if old.start_date != series.start_date or old.rule != series.rule:
            # we don't use series.update_activities() here because we want to remove and collect participants
            for activity, date in series.get_matched_activities():
                if not activity:
                    series.create_activity(date)
                elif not date:
                    for user in activity.participants.all():
                        add_removed(activity, user)
                    activity.delete()

        after_data = ActivitySeriesHistorySerializer(series).data

        history = None

        if before_data != after_data:
            # TODO: store who was removed?
            history = History.objects.create(
                typus=HistoryTypus.SERIES_MODIFY,
                group=series.place.group,
                place=series.place,
                series=series,
                users=[self.context["request"].user],
                # TODO: this doesn't include the changed participant_types as we popped it above...
                payload={k: self.initial_data.get(k) for k in validated_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )

        if len(removed) > 0:
            removed.sort(key=lambda val: val["activity"].date.start)

            # collect unique activities
            activities = {}
            for entry in removed:
                activity = entry["activity"]
                if activity.id not in activities:
                    # we might have deleted some of the activities by the time the task is run, so store as dict
                    activities[activity.id] = model_to_dict(activity)

            notify_participant_removals(
                activity_type_id=series.activity_type.id,
                place_id=series.place.id,
                activities_data=list(activities.values()),
                participants=[{"user": entry["user"].id, "activity": entry["activity"].id} for entry in removed],
                message=updated_message,
                removed_by_id=self.context["request"].user.id,
                history_id=history.id if history else None,
            )

        series.place.group.refresh_active_status()

        return series


class ActivityParticipantUpdateCheckSerializer(ActivityParticipantSerializer):
    class Meta:
        model = ActivityParticipant
        fields = [
            "user",
            "activity",
        ]
        read_only_fields = [
            "user",
            "activity",
        ]


class ActivitySeriesUpdateCheckSerializer(Serializer):
    # request fields
    rule = serializers.CharField(write_only=True, required=False)
    start_date = DateTimeFieldWithTimezone(write_only=True, required=False)
    participant_types = SeriesParticipantTypeSerializer(many=True, write_only=True, required=False)

    # response fields
    participants = ActivityParticipantUpdateCheckSerializer(many=True, read_only=True)
    activities = ActivitySerializer(many=True, read_only=True)

    def update(self, instance, validated_data):
        series = instance

        will_remove_participant_ids = set()

        if "start_date" in validated_data or "rule" in validated_data:
            # we set the values on the series, so we can calculate the dates
            # don't save it!!!
            if "start_date" in validated_data:
                series.start_date = validated_data["start_date"]
            if "rule" in validated_data:
                series.rule = validated_data["rule"]
            for activity, date in series.get_matched_activities():
                if activity and not date:
                    if activity.activityparticipant_set.count() > 0:
                        # would remove these participants!
                        will_remove_participant_ids.update(
                            activity.activityparticipant_set.values_list("id", flat=True)
                        )

        if "participant_types" in validated_data:
            activities = series.activities.upcoming()
            for entry in validated_data["participant_types"]:
                pk = entry.pop("id", None)
                if pk:
                    # existing series participant type
                    series_participant_type = SeriesParticipantType.objects.get(pk=pk)
                    if entry.get("_removed", False):
                        # existing series participant type would be deleted
                        will_remove_participant_ids.update(
                            ActivityParticipant.objects.filter(
                                activity__in=activities,
                                participant_type__series_participant_type=series_participant_type,
                            ).values_list("id", flat=True)
                        )
                    else:
                        old_role = series_participant_type.role
                        role = entry.get("role", None)
                        role_changed = "role" in entry and role != old_role

                        if role_changed:
                            # now we go through all the related participant types for the individual activities
                            for participant_type in ParticipantType.objects.filter(
                                series_participant_type_id=pk,
                                activity__in=activities,
                            ):
                                if role_changed and participant_type.role == old_role:
                                    participant_type.role = role
                                    # find all the participants who are missing the new role
                                    users_with_new_role = series.place.group.members.filter(
                                        groupmembership__roles__contains=[role]
                                    )
                                    will_remove_participant_ids.update(
                                        ActivityParticipant.objects.filter(
                                            participant_type=participant_type,
                                            activity__in=activities,
                                        )
                                        .exclude(
                                            user__in=users_with_new_role,
                                        )
                                        .values_list("id", flat=True)
                                    )

        return {
            "participants": ActivityParticipant.objects.filter(id__in=will_remove_participant_ids),
            "activities": Activity.objects.filter(activityparticipant__id__in=will_remove_participant_ids),
        }

    def create(self, validated_data):
        pass
