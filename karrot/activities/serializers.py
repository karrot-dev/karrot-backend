import dateutil.rrule
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import DateTimeField, Field
from rest_framework.validators import UniqueTogetherValidator
from rest_framework_csv.renderers import CSVRenderer

from karrot.base.base_models import CustomDateTimeTZRange
from karrot.history.models import History, HistoryTypus
from karrot.activities import stats
from karrot.activities.models import (
    Activity as ActivityModel, Feedback as FeedbackModel, ActivitySeries as ActivitySeriesModel, ActivityType
)
from karrot.utils.date_utils import csv_datetime
from karrot.utils.misc import find_changed


class ActivityTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityType
        fields = '__all__'


class ActivityHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = '__all__'


class DateTimeFieldWithTimezone(DateTimeField):
    def get_attribute(self, instance):
        value = super().get_attribute(instance)
        if hasattr(instance, 'timezone'):
            return value.astimezone(instance.timezone)
        return value

    def enforce_timezone(self, value):
        if timezone.is_aware(value):
            return value
        return super().enforce_timezone(value)


class DateTimeRangeField(serializers.Field):
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


class ActivitySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = [
            'id',
            'typus',
            'date',
            'series',
            'place',
            'max_participants',
            'participants',
            'description',
            'feedback_due',
            'feedback_given_by',
            'is_disabled',
            'has_duration',
            'is_done',
        ]
        read_only_fields = [
            'id',
            'series',
            'participants',
            'is_done',
        ]

    participants = serializers.SerializerMethodField()
    feedback_due = DateTimeFieldWithTimezone(read_only=True)

    date = DateTimeRangeField()

    def get_participants(self, activity):
        return [c.user_id for c in activity.activityparticipant_set.all()]

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    def create(self, validated_data):
        activity = super().create(validated_data)
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

    def validate_place(self, place):
        if not place.group.is_editor(self.context['request'].user):
            if not place.group.is_member(self.context['request'].user):
                raise PermissionDenied('You are not member of the place\'s group.')
            raise PermissionDenied(_('You need to be a group editor'))
        return place

    def validate_date(self, date):
        if not date.start > timezone.now() + timedelta(minutes=10):
            raise serializers.ValidationError(_('The date should be in the future.'))
        duration = date.end - date.start
        if duration < timedelta(seconds=1):
            raise serializers.ValidationError('Duration must be at least one second.')
        return date

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        typus = data.get('typus', get_instance_attr('typus'))
        place = data.get('place', get_instance_attr('place'))

        if typus and place and typus.group_id != place.group_id:
            raise serializers.ValidationError(_('Typus is not for this group.'))

        return data


class ActivityUpdateSerializer(ActivitySerializer):
    class Meta:
        model = ActivityModel
        fields = ActivitySerializer.Meta.fields
        read_only_fields = ActivitySerializer.Meta.read_only_fields + ['place']

    date = DateTimeRangeField()

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

    def validate_date(self, date):
        if self.instance.series is not None and abs((self.instance.date.start - date.start).total_seconds()) > 1:
            raise serializers.ValidationError(_('You can\'t move pickups that are part of a series.'))
        return super().validate_date(date)

    def validate_has_duration(self, has_duration):
        if self.instance.series is not None and has_duration != self.instance.has_duration:
            raise serializers.ValidationError('You cannot modify the duration of activities that are part of a series')
        return has_duration


class ActivityJoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivityModel
        fields = []

    def update(self, activity, validated_data):
        user = self.context['request'].user
        activity.add_participant(user)

        stats.activity_joined(activity)

        History.objects.create(
            typus=HistoryTypus.ACTIVITY_JOIN,
            group=activity.place.group,
            place=activity.place,
            activity=activity,
            users=[
                user,
            ],
            payload=ActivitySerializer(instance=activity).data,
        )
        activity.place.group.refresh_active_status()
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


class DurationInSecondsField(Field):
    default_error_messages = {}

    def __init__(self, **kwargs):
        super(DurationInSecondsField, self).__init__(**kwargs)

    def to_internal_value(self, value):
        return timedelta(seconds=value)

    def to_representation(self, value):
        return value.seconds


class ActivitySeriesHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = '__all__'


class ActivitySeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = [
            'id',
            'typus',
            'max_participants',
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

    duration = DurationInSecondsField(required=False, allow_null=True)

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    @transaction.atomic()
    def create(self, validated_data):
        series = super().create(validated_data)

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

    def validate_place(self, place):
        if not place.group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
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
            raise serializers.ValidationError(_('Invalid recurrence rule.'))
        if not isinstance(rrule, dateutil.rrule.rrule):
            raise serializers.ValidationError(_('Only single recurrence rules are allowed.'))
        return rule_string

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        typus = data.get('typus', get_instance_attr('typus'))
        place = data.get('place', get_instance_attr('place'))

        if typus and place and typus.group_id != place.group_id:
            raise serializers.ValidationError(_('Typus is not for this group.'))

        return data


class ActivitySeriesUpdateSerializer(ActivitySeriesSerializer):
    class Meta:
        model = ActivitySeriesModel
        fields = ActivitySeriesSerializer.Meta.fields
        read_only_fields = ActivitySeriesSerializer.Meta.read_only_fields + ['place']

    duration = DurationInSecondsField(required=False, allow_null=True)

    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance
        return super().save(**kwargs)

    @transaction.atomic()
    def update(self, series, validated_data):
        before_data = ActivitySeriesHistorySerializer(series).data
        super().update(series, validated_data)
        after_data = ActivitySeriesHistorySerializer(series).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.SERIES_MODIFY,
                group=series.place.group,
                place=series.place,
                series=series,
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        series.place.group.refresh_active_status()
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

    def get_is_editable(self, feedback):
        return feedback.about.is_recent() and feedback.given_by_id == self.context['request'].user.id

    def validate_about(self, about):
        user = self.context['request'].user
        group = about.place.group
        if not group.is_member(user):
            raise serializers.ValidationError('You are not member of the place\'s group.')
        if about.is_upcoming():
            raise serializers.ValidationError(_('The pickup is not done yet'))
        if not about.is_participant(user):
            raise serializers.ValidationError(_('You aren\'t assigned to the pickup.'))
        if not about.is_recent():
            raise serializers.ValidationError(
                _('You can\'t give feedback for pickups more than %(days_number)s days ago.') %
                {'days_number': settings.FEEDBACK_POSSIBLE_DAYS}
            )
        return about

    def validate(self, data):
        def get_instance_attr(field):
            if self.instance is None:
                return None
            return getattr(self.instance, field)

        comment = data.get('comment', get_instance_attr('comment'))
        weight = data.get('weight', get_instance_attr('weight'))
        if (comment is None or comment == '') and weight is None:
            raise serializers.ValidationError(_('Both comment and weight cannot be blank.'))
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

    def get_about_date(self, feedback):
        activity = feedback.about
        group = activity.place.group

        return csv_datetime(activity.date.start.astimezone(group.timezone))

    def get_about_place(self, feedback):
        return feedback.about.place_id

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
