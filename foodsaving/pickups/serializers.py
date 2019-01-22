import dateutil.rrule
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import DateTimeField
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.base.base_models import CustomDateTimeTZRange
from foodsaving.history.models import History, HistoryTypus
from foodsaving.pickups import stats
from foodsaving.pickups.models import (
    PickupDate as PickupDateModel, Feedback as FeedbackModel, PickupDateSeries as PickupDateSeriesModel
)
from foodsaving.utils.misc import find_changed


class PickupDateHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateModel
        fields = '__all__'


class DateTimeRangeField(serializers.Field):
    child = DateTimeField()

    default_error_messages = {
        'list': _('Must be a list'),
        'length': _('Must be a list with one or two values'),
        'required': _('Must pass start value'),
    }

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


class PickupDateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateModel
        fields = [
            'id',
            'date',
            'series',
            'store',
            'max_collectors',
            'collector_ids',
            'description',
            'feedback_due',
            'feedback_given_by',
            'is_disabled',
        ]
        read_only_fields = [
            'id',
            'series',
            'collector_ids',
        ]

    # TODO change to collectors to make it uniform with other endpoints
    collector_ids = serializers.SerializerMethodField()
    feedback_due = serializers.DateTimeField(read_only=True)

    date = DateTimeRangeField()

    def get_collector_ids(self, pickup):
        return [c.user_id for c in pickup.pickupdatecollector_set.all()]

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    def create(self, validated_data):
        pickupdate = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.PICKUP_CREATE,
            group=pickupdate.store.group,
            store=pickupdate.store,
            pickup=pickupdate,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            after=PickupDateHistorySerializer(pickupdate).data,
        )
        pickupdate.store.group.refresh_active_status()
        return pickupdate

    def validate_store(self, store):
        if not self.context['request'].user.groups.filter(store=store).exists():
            raise PermissionDenied(_('You are not member of the store\'s group.'))
        if not store.group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        return store

    def validate_date(self, date):
        if not date.start > timezone.now() + timedelta(minutes=10):
            raise serializers.ValidationError(_('The date should be in the future.'))
        return date


class PickupDateUpdateSerializer(PickupDateSerializer):
    class Meta:
        model = PickupDateModel
        fields = PickupDateSerializer.Meta.fields
        read_only_fields = PickupDateSerializer.Meta.read_only_fields + ['store']

    date = DateTimeRangeField()

    def save(self, **kwargs):
        pickupdate = self.instance
        changed_data = find_changed(pickupdate, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        before_data = PickupDateHistorySerializer(pickupdate).data
        pickupdate = super().save(**kwargs)
        after_data = PickupDateHistorySerializer(pickupdate).data

        if before_data != after_data:
            typus_list = []
            if 'is_disabled' in changed_data:
                if changed_data['is_disabled']:
                    typus_list.append(HistoryTypus.PICKUP_DISABLE)
                    stats.pickup_disabled(pickupdate)
                else:
                    typus_list.append(HistoryTypus.PICKUP_ENABLE)
                    stats.pickup_enabled(pickupdate)

            if len(set(changed_data.keys()).difference(['is_disabled'])) > 0:
                typus_list.append(HistoryTypus.PICKUP_MODIFY)

            for typus in typus_list:
                History.objects.create(
                    typus=typus,
                    group=pickupdate.store.group,
                    store=pickupdate.store,
                    pickup=pickupdate,
                    users=[
                        self.context['request'].user,
                    ],
                    payload={k: self.initial_data.get(k)
                             for k in changed_data.keys()},
                    before=before_data,
                    after=after_data,
                )
        pickupdate.store.group.refresh_active_status()

        return pickupdate

    def validate_date(self, date):
        if self.instance.series is not None and abs((self.instance.date.start - date.start).total_seconds()) > 1:
            raise serializers.ValidationError(_('You can\'t move pickups that are part of a series.'))
        return super().validate_date(date)


class PickupDateJoinSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateModel
        fields = []

    def update(self, pickupdate, validated_data):
        user = self.context['request'].user
        pickupdate.add_collector(user)

        stats.pickup_joined(pickupdate)

        History.objects.create(
            typus=HistoryTypus.PICKUP_JOIN,
            group=pickupdate.store.group,
            store=pickupdate.store,
            users=[
                user,
            ],
            payload=PickupDateSerializer(instance=pickupdate).data,
        )
        pickupdate.store.group.refresh_active_status()
        return pickupdate


class PickupDateLeaveSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateModel
        fields = []

    def update(self, pickupdate, validated_data):
        user = self.context['request'].user
        pickupdate.remove_collector(user)

        stats.pickup_left(pickupdate)

        History.objects.create(
            typus=HistoryTypus.PICKUP_LEAVE,
            group=pickupdate.store.group,
            store=pickupdate.store,
            users=[
                user,
            ],
            payload=PickupDateSerializer(instance=pickupdate).data,
        )
        pickupdate.store.group.refresh_active_status()
        return pickupdate


class PickupDateSeriesHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateSeriesModel
        fields = '__all__'


class PickupDateSeriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateSeriesModel
        fields = [
            'id',
            'max_collectors',
            'store',
            'rule',
            'start_date',
            'description',
            'dates_preview',
        ]
        read_only_fields = [
            'id',
        ]

    dates_preview = serializers.ListField(
        child=serializers.DateTimeField(),
        read_only=True,
        source='dates',
    )

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    @transaction.atomic()
    def create(self, validated_data):
        series = super().create(validated_data)

        History.objects.create(
            typus=HistoryTypus.SERIES_CREATE,
            group=series.store.group,
            store=series.store,
            series=series,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            after=PickupDateSeriesHistorySerializer(series).data,
        )
        series.store.group.refresh_active_status()
        return series

    def validate_store(self, store):
        if not store.group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        if not store.group.is_member(self.context['request'].user):
            raise serializers.ValidationError(_('You are not member of the store\'s group.'))
        return store

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


class PickupDateSeriesUpdateSerializer(PickupDateSeriesSerializer):
    class Meta:
        model = PickupDateSeriesModel
        fields = PickupDateSeriesSerializer.Meta.fields
        read_only_fields = PickupDateSeriesSerializer.Meta.read_only_fields + ['store']

    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance
        return super().save(**kwargs)

    @transaction.atomic()
    def update(self, series, validated_data):
        before_data = PickupDateSeriesHistorySerializer(series).data
        super().update(series, validated_data)
        after_data = PickupDateSeriesHistorySerializer(series).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.SERIES_MODIFY,
                group=series.store.group,
                store=series.store,
                series=series,
                users=[
                    self.context['request'].user,
                ],
                payload={k: self.initial_data.get(k)
                         for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        series.store.group.refresh_active_status()
        return series


class FeedbackSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedbackModel
        fields = ['id', 'weight', 'comment', 'about', 'given_by', 'created_at', 'is_editable']
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
        feedback.about.store.group.refresh_active_status()
        return feedback

    def update(self, feedback, validated_data):
        super().update(feedback, validated_data)
        feedback.about.store.group.refresh_active_status()
        return feedback

    def get_is_editable(self, feedback):
        return feedback.about.is_recent() and feedback.given_by_id == self.context['request'].user.id

    def validate_about(self, about):
        user = self.context['request'].user
        group = about.store.group
        if not group.is_member(user):
            raise serializers.ValidationError(_('You are not member of the store\'s group.'))
        if about.is_upcoming():
            raise serializers.ValidationError(_('The pickup is not done yet'))
        if not about.is_collector(user):
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
        if (comment is None or comment is '') and weight is None:
            raise serializers.ValidationError(_('Both comment and weight cannot be blank.'))
        data['given_by'] = self.context['request'].user
        return data
