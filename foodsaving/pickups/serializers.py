from datetime import timedelta

import dateutil.rrule
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.validators import UniqueTogetherValidator

from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils.misc import find_changed
from foodsaving.pickups import stats
from foodsaving.pickups.models import (
    PickupDate as PickupDateModel,
    Feedback as FeedbackModel,
    PickupDateSeries as PickupDateSeriesModel,
)


class PickupDateHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateModel
        fields = '__all__'


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
            'cancelled_at',
            'last_changed_by',
            'last_changed_message',
            'deleted',
        ]
        read_only_fields = [
            'id',
            'series',
            'collector_ids',
            'cancelled_at',
            'last_changed_by',
        ]

    # TODO change to collectors to make it uniform with other endpoints
    collector_ids = serializers.PrimaryKeyRelatedField(source='collectors', many=True, read_only=True)

    def save(self, **kwargs):
        return super().save(
            last_changed_by=self.context['request'].user,
            last_changed_message=self.validated_data.get('last_changed_message', ''),
        )

    def create(self, validated_data):
        pickupdate = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.PICKUP_CREATE,
            group=pickupdate.store.group,
            store=pickupdate.store,
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
        if not date > timezone.now() + timedelta(minutes=10):
            raise serializers.ValidationError(_('The date should be in the future.'))
        return date


class PickupDateUpdateSerializer(PickupDateSerializer):
    class Meta:
        model = PickupDateModel
        fields = PickupDateSerializer.Meta.fields
        read_only_fields = PickupDateSerializer.Meta.read_only_fields + ['store']

    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(set(self.validated_data.keys()).difference(['last_changed_message'])) == 0
        if skip_update:
            return self.instance
        return super().save(**kwargs)

    def update(self, pickupdate, validated_data):
        before_data = PickupDateHistorySerializer(pickupdate).data
        super().update(pickupdate, validated_data)
        after_data = PickupDateHistorySerializer(pickupdate).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.PICKUP_MODIFY,
                group=pickupdate.store.group,
                store=pickupdate.store,
                users=[
                    self.context['request'].user,
                ],
                payload={k: self.initial_data.get(k)
                         for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        pickupdate.store.group.refresh_active_status()
        return pickupdate


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
            'last_changed_message',
            'last_changed_by',
        ]
        read_only_fields = [
            'id',
            'last_changed_by',
        ]

    def save(self, **kwargs):
        return super().save(
            last_changed_by=self.context['request'].user,
            last_changed_message=self.validated_data.get('last_changed_message', ''),
        )

    @transaction.atomic()
    def create(self, validated_data):
        series = super().create(validated_data)

        History.objects.create(
            typus=HistoryTypus.SERIES_CREATE,
            group=series.store.group,
            store=series.store,
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
        skip_update = len(set(self.validated_data.keys()).difference(['last_changed_message'])) == 0
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

    def validate(self, attrs):
        series = self.instance
        last_changed_message = attrs.get('last_changed_message', '')
        rule = attrs.get('rule')
        start_date = attrs.get('start_date')
        values_changed = rule != series.rule or start_date != series.start_date
        if values_changed and last_changed_message == '':
            preview = series.preview_override_pickups(rule=rule, start_date=start_date)
            if any(pickup is not None and date is None and pickup.collectors.count() > 0
                   for (pickup, date) in preview):
                pass
                # raise serializers.ValidationError(code='required', detail={
                #     'last_changed_message':
                #     _('You need to provide a message to cancel pickups')
                # },)
        return super().validate(attrs)


class PickupDateSeriesCancelSerializer(serializers.ModelSerializer):
    class Meta:
        model = PickupDateSeriesModel
        fields = [
            'id',
            'last_changed_message',
        ]
        extra_kwargs = {'last_changed_message': {'allow_blank': False, 'required': True}}

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user, **kwargs)

    @transaction.atomic()
    def update(self, series, validated_data):
        # set last_changed_by and last_changed_message
        super().update(series, validated_data)
        payload = PickupDateSeriesSerializer(series).data
        before = PickupDateSeriesHistorySerializer(series).data

        # now delete series. this cancels associated pickups and sends a message to collectors
        series.delete()

        History.objects.create(
            typus=HistoryTypus.SERIES_DELETE,
            group=series.store.group,
            store=series.store,
            users=[
                self.context['request'].user,
            ],
            payload=payload,
            before=before,
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
