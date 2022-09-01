from typing import List

import dateutil.rrule
from datetime import timedelta, datetime

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from icalendar import vCalAddress, vText
from django.contrib.auth import get_user_model
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import CharField, DateTimeField, Field
from rest_framework.validators import UniqueTogetherValidator
from rest_framework_csv.renderers import CSVRenderer

from karrot.base.base_models import CustomDateTimeTZRange
from karrot.history.models import History, HistoryTypus
from karrot.activities import stats
from karrot.activities.models import (
    Activity as ActivityModel, Feedback as FeedbackModel, ActivitySeries as ActivitySeriesModel, ActivityType,
    ActivityParticipant, ParticipantType, SeriesParticipantType, default_duration
)
from karrot.utils.date_utils import csv_datetime
from karrot.utils.misc import find_changed


class ActivityTypeSerializer(serializers.ModelSerializer):
    updated_message = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = ActivityType
        fields = [
            'id',
            'name',
            'name_is_translatable',
            'colour',
            'icon',
            'has_feedback',
            'has_feedback_weight',
            'feedback_icon',
            'status',
            'group',
            "created_at",
            'updated_at',
            'updated_message',
            'group',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied('You are not a member of this group.')
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied('You need to be a group editor')
        return group

    def save(self, **kwargs):
        if not self.instance:
            return super().save(**kwargs)

        updated_message = self.validated_data.pop('updated_message', None)

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
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in changed_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )
        return activity_type

    def create(self, validated_data):
        activity_type = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.ACTIVITY_TYPE_CREATE,
            group=activity_type.group,
            users=[self.context['request'].user],
            payload=self.initial_data,
            after=ActivityTypeHistorySerializer(activity_type).data,
        )
        return activity_type


class ActivityTypeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = '__all__'


class DateTimeFieldWithTimezone(DateTimeField):
    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if value is None:
            return None
        if hasattr(instance, 'timezone'):
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
        'list': _('Must be a list'),
        'length': _('Must be a list with one or two values'),
        'required': _('Must pass start value'),
    }

    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if hasattr(instance, 'timezone'):
            return value.astimezone(instance.timezone)
        return value

    def to_representation(self, value):
        return [
            self.child.to_representation(value.lower),
            self.child.to_representation(value.upper),
        ]

    def to_internal_value(self, data):
        if not isinstance(data, list):
            self.fail('list')
        if not 0 < len(data) <= 2:
            self.fail('length')
        lower = data[0]
        upper = data[1] if len(data) > 1 else None
        lower = self.child.to_internal_value(lower) if lower else None
        upper = self.child.to_internal_value(upper) if upper else None
        if not lower:
            self.fail('required')
        upper = lower + timedelta(minutes=30) if not upper else upper
        return CustomDateTimeTZRange(lower, upper)


class ActivityParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityParticipant
        fields = [
            'user',
            'participant_type',
            'created_at',
        ]
        read_only_fields = [
            'user',
            'participant_type',
            'created_at',
        ]


class ParticipantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParticipantType
        fields = [
            'id',
            'description',
            'max_participants',
            'series_participant_type',
            'role',
            '_removed',
        ]

    id = serializers.IntegerField(required=False)
    _removed = serializers.BooleanField(required=False)


class ActivityHistorySerializer(serializers.ModelSerializer):
    participant_types = ParticipantTypeSerializer(many=True)

    class Meta:
        model = ActivityModel
        fields = '__all__'


class SeriesParticipantTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeriesParticipantType
        fields = [
            'id',
            'description',
            'max_participants',
            'role',
            '_removed',
        ]

    id = serializers.IntegerField(required=False)
    _removed = serializers.BooleanField(required=False)


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = [
            'id',
            'activity_type',
            'date',
            'series',
            'place',
            'participant_types',
            'participants',
            'description',
            'feedback_due',
            'feedback_given_by',
            'feedback_dismissed_by',
            'is_disabled',
            'has_duration',
            'is_done',
        ]
        read_only_fields = [
            'id',
            'series',
            'is_done',
        ]

    participants = ActivityParticipantSerializer(
        read_only=True,
        source='activityparticipant_set',
        many=True,
    )
    participant_types = ParticipantTypeSerializer(many=True)

    feedback_dismissed_by = serializers.SerializerMethodField()
    feedback_due = DateTimeFieldWithTimezone(read_only=True, allow_null=True)

    date = DateTimeRangeField()

    def get_feedback_dismissed_by(self, activity) -> List[int]:
        # we are filtering in python to make use of prefetched data
        return [c.user_id for c in activity.activityparticipant_set.all() if c.feedback_dismissed]

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    def create(self, validated_data):
        participant_types_data = validated_data.pop('participant_types')
        activity = super().create(validated_data)
        for participant_type_data in participant_types_data:
            # creating the nested data
            activity.participant_types.create(**participant_type_data)

        History.objects.create(
            typus=HistoryTypus.ACTIVITY_CREATE,
            group=activity.place.group,
            place=activity.place,
            activity=activity,
            users=[self.context['request'].user],
            payload=self.initial_data,
            after=ActivityHistorySerializer(activity).data,
        )
        activity.place.group.refresh_active_status()
        return activity

    def validate_activity_type(self, activity_type):
        if activity_type.status != 'active':
            raise serializers.ValidationError('You can only create activities for active types')
        return activity_type

    def validate_place(self, place):
        if not place.group.is_editor(self.context['request'].user):
            if not place.group.is_member(self.context['request'].user):
                raise PermissionDenied('You are not member of the place\'s group.')
            raise PermissionDenied('You need to be a group editor')
        return place

    def validate_date(self, date):
        if not date.start > timezone.now() + timedelta(minutes=10):
            raise serializers.ValidationError('The date should be in the future.')
        duration = date.end - date.start
        if duration < timedelta(seconds=1):
            raise serializers.ValidationError('Duration must be at least one second.')
        return date

    def validate_participant_types(self, participant_types):
        for participant_type in participant_types:
            series_participant_type = participant_type.get('series_participant_type', None)
            if series_participant_type:
                if not self.instance:
                    # invalid to specify this, as these are only created by a karrot task, not by API
                    raise serializers.ValidationError('Cannot specify series_participant_type for new activity.')
                if series_participant_type.activity_series_id != self.instance.series_id:
                    raise serializers.ValidationError('Wrong series.')
        return participant_types

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity_type = data.get('activity_type', get_instance_attr('activity_type'))
        place = data.get('place', get_instance_attr('place'))

        if activity_type and place and activity_type.group_id != place.group_id:
            raise serializers.ValidationError('ActivityType is not for this group.')

        return data


class ActivityUpdateSerializer(ActivitySerializer):
    class Meta:
        model = ActivityModel
        fields = ActivitySerializer.Meta.fields
        read_only_fields = ActivitySerializer.Meta.read_only_fields + ['place']

    date = DateTimeRangeField()

    @transaction.atomic()
    def save(self, **kwargs):
        activity = self.instance
        changed_data = find_changed(activity, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        before_data = ActivityHistorySerializer(activity).data
        activity = super().save(**kwargs)
        after_data = ActivityHistorySerializer(activity).data

        if before_data != after_data:
            typus_list = []
            if 'is_disabled' in changed_data:
                if changed_data['is_disabled']:
                    typus_list.append(HistoryTypus.ACTIVITY_DISABLE)
                    stats.activity_disabled(activity)
                else:
                    typus_list.append(HistoryTypus.ACTIVITY_ENABLE)
                    stats.activity_enabled(activity)

            if len(set(changed_data.keys()).difference(['is_disabled'])) > 0:
                typus_list.append(HistoryTypus.ACTIVITY_MODIFY)

            for typus in typus_list:
                History.objects.create(
                    typus=typus,
                    group=activity.place.group,
                    place=activity.place,
                    activity=activity,
                    users=[self.context['request'].user],
                    payload={k: self.initial_data.get(k)
                             for k in changed_data.keys()},
                    before=before_data,
                    after=after_data,
                )
        activity.place.group.refresh_active_status()

        return activity

    def update(self, instance, validated_data):
        activity = instance
        participant_types = validated_data.pop('participant_types', None)
        if participant_types:
            for entry in participant_types:
                pk = entry.pop('id', None)
                if pk:
                    # existing participant type
                    participant_type = ParticipantType.objects.get(pk=pk)
                    if entry.get('_removed', False):
                        # existing participant type being deleted
                        # TODO: maybe send these users a notification to say they were removed?
                        activity.activityparticipant_set \
                            .filter(participant_type=participant_type) \
                            .delete()
                        participant_type.delete()
                    else:
                        # existing participant type being edited
                        role = entry.get('role', None)
                        if role and role != participant_type.role:
                            # find all the participants who are missing the new role, and remove them...
                            # TODO: perhaps a notification, or option, message...
                            users = activity.place.group.members.filter(groupmembership__roles__contains=[role])
                            activity.activityparticipant_set\
                                .filter(participant_type=participant_type)\
                                .exclude(user__in=users)\
                                .delete()

                        # update the rest of the fields
                        ParticipantType.objects.filter(pk=pk).update(**entry)
                else:
                    # new participant type \o/
                    ParticipantType.objects.create(activity=activity, **entry)
        return super().update(instance, validated_data)

    def validate_date(self, date):
        if self.instance.series is not None and abs((self.instance.date.start - date.start).total_seconds()) > 1:
            raise serializers.ValidationError('You can\'t move activities that are part of a series.')
        return super().validate_date(date)

    def validate_has_duration(self, has_duration):
        if self.instance.series is not None and has_duration != self.instance.has_duration:
            raise serializers.ValidationError('You cannot modify the duration of activities that are part of a series')
        return has_duration


class ActivityICSSerializer(serializers.ModelSerializer):
    """serializes an activity to the ICS format, in conjunction with the ICSEventRenderer.

    details of the allowed fields:
    https://www.kanzaki.com/docs/ical/vevent.html"""
    class Meta:
        model = ActivityModel
        fields = [
            'uid', 'dtstamp', 'summary', 'description', 'dtstart', 'dtend', 'transp', 'categories', 'location', 'geo',
            'attendee', 'status'
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
    dtstart = DateTimeField(source='date.start', format=None)
    # end date
    dtend = DateTimeField(source='date.end', format=None)
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
        return datetime.now()

    def get_uid(self, activity):
        request = self.context.get('request')
        domain = 'karrot'
        if request and request.META.get('HTTP_HOST'):
            domain = request.META.get('HTTP_HOST')
        return 'activity_{}@{}'.format(activity.id, domain)

    def get_status(self, activity):
        return 'CANCELLED' if activity.is_disabled else 'CONFIRMED'

    def get_summary(self, activity):
        return '{}: {}'.format(activity.activity_type.name, activity.place.name)

    def get_transp(self, activity):
        return 'OPAQUE'

    def get_categories(self, activity):
        return [activity.activity_type.name]

    def get_location(self, activity):
        return activity.place.name

    def get_geo(self, activity):
        place = activity.place
        return (place.latitude, place.longitude) if place.latitude is not None else None

    def get_attendee(self, activity):
        attendees = []
        for attendee in get_user_model().objects.filter(activityparticipant__activity=activity):
            address = vCalAddress(attendee.email)
            address.params['cn'] = vText(attendee.get_full_name())
            address.params['role'] = vText('REQ-PARTICIPANT')
            address.params['partstat'] = vText('ACCEPTED')
            attendees.append(address)
        return attendees


class ActivityJoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = [
            'participant_type',
        ]

    participant_type = serializers.IntegerField(write_only=True, default=None)

    def update(self, activity, validated_data):
        user = self.context['request'].user
        place = activity.place
        group = place.group

        pt_id = validated_data.get('participant_type', None)
        if pt_id:
            participant_type = activity.participant_types.get(id=pt_id)
        else:
            # if not supplied, and the activity has only 1, use that one
            if activity.participant_types.count() > 1:
                raise PermissionDenied('Must supply participant_type')
            participant_type = activity.participant_types.first()

        # check the user has the role
        if not group.is_member_with_role(user, participant_type.role):
            raise PermissionDenied('You do not have the required role.')

        # check there is space available
        if participant_type.is_full():
            raise PermissionDenied('Activity is already full.')

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
        user = self.context['request'].user
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
        user = self.context['request'].user
        activity.dismiss_feedback(user)

        stats.feedback_dismissed(activity)

        activity.place.group.refresh_active_status()
        return activity


@extend_schema_field(OpenApiTypes.INT)
class DurationInSecondsField(Field):
    default_error_messages = {}

    def __init__(self, **kwargs):
        super(DurationInSecondsField, self).__init__(**kwargs)

    def to_internal_value(self, value):
        return timedelta(seconds=value)

    def to_representation(self, value):
        return value.seconds


class ActivitySeriesHistorySerializer(serializers.ModelSerializer):
    participant_types = SeriesParticipantTypeSerializer(many=True)

    class Meta:
        model = ActivitySeriesModel
        fields = '__all__'


class ActivitySeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = [
            'id',
            'activity_type',
            'participant_types',
            'place',
            'rule',
            'start_date',
            'description',
            'dates_preview',
            'duration',
        ]
        read_only_fields = [
            'id',
        ]

    start_date = DateTimeFieldWithTimezone()
    dates_preview = serializers.ListField(
        child=DateTimeFieldWithTimezone(),
        read_only=True,
        source='dates',
    )

    participant_types = SeriesParticipantTypeSerializer(many=True)

    duration = DurationInSecondsField(required=False, allow_null=True)

    @transaction.atomic()
    def create(self, validated_data):
        participant_types_data = validated_data.pop('participant_types')
        series = super().create(validated_data)
        for participant_type_data in participant_types_data:
            # creating the nested data
            series.participant_types.create(**participant_type_data)
        series.update_activities()

        History.objects.create(
            typus=HistoryTypus.SERIES_CREATE,
            group=series.place.group,
            place=series.place,
            series=series,
            users=[self.context['request'].user],
            payload=self.initial_data,
            after=ActivitySeriesHistorySerializer(series).data,
        )
        series.place.group.refresh_active_status()
        return series

    def validate_activity_type(self, activity_type):
        if activity_type.status != 'active':
            raise serializers.ValidationError('You can only create series for active types')
        return activity_type

    def validate_place(self, place):
        if not place.group.is_editor(self.context['request'].user):
            raise PermissionDenied('You need to be a group editor')
        if not place.group.is_member(self.context['request'].user):
            raise serializers.ValidationError('You are not member of the place\'s group.')
        return place

    def validate_start_date(self, date):
        date = date.replace(second=0, microsecond=0)
        return date

    def validate_rule(self, rule_string):
        try:
            rrule = dateutil.rrule.rrulestr(rule_string)
        except ValueError:
            raise serializers.ValidationError('Invalid recurrence rule.')
        if not isinstance(rrule, dateutil.rrule.rrule):
            raise serializers.ValidationError('Only single recurrence rules are allowed.')
        return rule_string

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity_type = data.get('activity_type', get_instance_attr('activity_type'))
        place = data.get('place', get_instance_attr('place'))

        if activity_type and place and activity_type.group_id != place.group_id:
            raise serializers.ValidationError('ActivityType is not for this group.')

        return data


class ActivitySeriesUpdateSerializer(ActivitySeriesSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = ActivitySeriesSerializer.Meta.fields
        read_only_fields = ActivitySeriesSerializer.Meta.read_only_fields + ['place']

    duration = DurationInSecondsField(required=False, allow_null=True)

    @transaction.atomic()
    def save(self, **kwargs):
        series = self.instance
        old = self.instance.old() if series else None
        changed_data = find_changed(series, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return series

        before_data = ActivitySeriesHistorySerializer(series).data
        series = super().save(last_changed_by=self.context['request'].user)
        after_data = ActivitySeriesHistorySerializer(series).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.SERIES_MODIFY,
                group=series.place.group,
                place=series.place,
                series=series,
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in changed_data.keys()},
                before=before_data,
                after=after_data,
            )

        series.place.group.refresh_active_status()

        if old.start_date != series.start_date or old.rule != series.rule:
            series.update_activities()

        return series

    def update(self, series, validated_data):
        activities = None

        description = validated_data.get('description', None)
        duration = validated_data.get('duration', None)
        participant_types = validated_data.pop('participant_types', None)

        description_changed = 'description' in validated_data and series.description != description
        duration_changed = 'duration' in validated_data and series.duration != duration
        if description_changed or duration_changed or participant_types:
            activities = series.activities.upcoming()
            for activity in activities:
                if description_changed and series.description == activity.description:
                    activity.description = description
                if duration_changed:
                    if duration:
                        activity.has_duration = True
                        activity.date = CustomDateTimeTZRange(activity.date.start, activity.date.start + duration)
                    else:
                        activity.has_duration = False
                        activity.date = CustomDateTimeTZRange(
                            activity.date.start, activity.date.start + default_duration
                        )
            if participant_types:
                for entry in participant_types:
                    pk = entry.pop('id', None)
                    if pk:
                        # existing series participant type
                        series_participant_type = SeriesParticipantType.objects.get(pk=pk)
                        if entry.get('_removed', False):
                            # existing series participant type being deleted
                            # TODO: maybe send these users a notification to say they were removed?
                            ActivityParticipant.objects.filter(
                                activity__in=activities,
                                participant_type__series_participant_type=series_participant_type,
                            ).delete()
                            ParticipantType.objects.filter(
                                series_participant_type=series_participant_type,
                                activity__in=activities,
                            ).delete()
                            series_participant_type.delete()
                        else:
                            # existing series participant type being edited
                            old_description = series_participant_type.description
                            description = entry.get('description', None)
                            description_changed = 'description' in entry and description != old_description

                            old_max_participants = series_participant_type.max_participants
                            max_participants = entry.get('max_participants', None)
                            max_participants_changed = 'max_participants' in entry and max_participants != old_max_participants

                            old_role = series_participant_type.role
                            role = entry.get('role', None)
                            role_changed = 'role' in entry and role != old_role

                            if description_changed or max_participants_changed or role_changed:
                                # now we go through all the related participant types for the individual activities
                                for participant_type in ParticipantType.objects.filter(
                                        series_participant_type_id=pk,
                                        activity__in=activities,
                                ):
                                    if description_changed and participant_type.description == old_description:
                                        participant_type.description = description
                                    if max_participants_changed and participant_type.max_participants == old_max_participants:
                                        participant_type.max_participants = max_participants
                                    if role_changed and participant_type.role == old_role:
                                        participant_type.role = role
                                        # find all the participants who are missing the new role, and remove them...
                                        # TODO: is this a good way to go about it? at least document it...
                                        users_with_new_role = series.place.group.members.filter(
                                            groupmembership__roles__contains=[role]
                                        )
                                        ActivityParticipant.objects.filter(
                                            participant_type=participant_type,
                                            activity__in=activities,
                                        ).exclude(user__in=users_with_new_role).delete()
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

        series = super().update(series, validated_data)

        if activities:
            # TODO: why do this after update not before?
            # TODO: this sends a storm of activity updates, and the frontend re-requests activities loads of times
            # ... could implement a bulk-update websocket message, would also need to for work update_activities()
            # we will have modified nested info in activities so trigger updates
            [activity.save() for activity in activities]

        return series


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackModel
        fields = [
            'id',
            'weight',
            'comment',
            'about',
            'given_by',
            'created_at',
            'is_editable',
        ]
        read_only_fields = ['given_by', 'created_at']
        extra_kwargs = {'given_by': {'default': serializers.CurrentUserDefault()}}
        validators = [
            UniqueTogetherValidator(
                queryset=FeedbackModel.objects.all(), fields=FeedbackModel._meta.unique_together[0]
            )
        ]

    is_editable = serializers.SerializerMethodField()

    def create(self, validated_data):
        feedback = super().create(validated_data)
        feedback.about.place.group.refresh_active_status()
        return feedback

    def update(self, feedback, validated_data):
        super().update(feedback, validated_data)
        feedback.about.place.group.refresh_active_status()
        return feedback

    def get_is_editable(self, feedback) -> bool:
        return feedback.about.is_recent() and feedback.given_by_id == self.context['request'].user.id

    def validate_about(self, about):
        user = self.context['request'].user
        group = about.place.group
        if not group.is_member(user):
            raise serializers.ValidationError('You are not member of the place\'s group.')
        if about.is_upcoming():
            raise serializers.ValidationError('The activity is not done yet')
        if not about.is_participant(user):
            raise serializers.ValidationError('You aren\'t assigned to the activity.')
        if not about.is_recent():
            raise serializers.ValidationError(
                'You can\'t give feedback for activities more than {} days ago.'.format(
                    settings.FEEDBACK_POSSIBLE_DAYS
                )
            )
        return about

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        activity_type = data.get('about', get_instance_attr('about')).activity_type

        comment = data.get('comment', get_instance_attr('comment'))
        weight = data.get('weight', get_instance_attr('weight'))

        if not activity_type.has_feedback:
            raise serializers.ValidationError(
                'You cannot give feedback to an activity of type {}.'.format(activity_type.name)
            )

        if weight is not None and not activity_type.has_feedback_weight:
            raise serializers.ValidationError(
                'You cannot give weight feedback to an activity of type {}.'.format(activity_type.name)
            )

        if (comment is None or comment == '') and weight is None:
            raise serializers.ValidationError('Both comment and weight cannot be blank.')

        data['given_by'] = self.context['request'].user
        return data


class FeedbackExportSerializer(FeedbackSerializer):
    class Meta:
        model = FeedbackModel
        fields = [
            'id',
            'about_place',
            'given_by',
            'about',
            'created_at',
            'about_date',
            'weight',
            'comment',
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
        'about_place': 'place_id',
        'about': 'activity_id',
        'given_by': 'user_id',
        'about_date': 'date',
    }
