from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils.misc import find_changed
from foodsaving.places.models import Place as PlaceModel, PlaceStatus, PlaceSubscription


class PlaceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceModel
        fields = '__all__'


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceModel
        fields = [
            'id',
            'name',
            'description',
            'group',
            'address',
            'latitude',
            'longitude',
            'weeks_in_advance',
            'status',
        ]
        extra_kwargs = {
            'name': {
                'min_length': 3,
            },
            'description': {
                'trim_whitespace': False,
                'max_length': settings.DESCRIPTION_MAX_LENGTH,
            },
        }
        read_only_fields = [
            'id',
        ]

    status = serializers.ChoiceField(
        choices=[status.value for status in PlaceStatus], default=PlaceModel.DEFAULT_STATUS
    )

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    def create(self, validated_data):
        place = super().create(validated_data)

        # TODO move into receiver
        History.objects.create(
            typus=HistoryTypus.STORE_CREATE,
            group=place.group,
            place=place,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            after=PlaceHistorySerializer(place).data,
        )
        place.group.refresh_active_status()
        return place

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        if not group.is_editor(self.context['request'].user):
            raise PermissionDenied(_('You need to be a group editor'))
        return group

    def validate_weeks_in_advance(self, w):
        if w < 1:
            raise serializers.ValidationError(_('Set at least one week in advance'))
        if w > settings.STORE_MAX_WEEKS_IN_ADVANCE:
            raise serializers.ValidationError(
                _('Do not set more than %(count)s weeks in advance') % {'count': settings.STORE_MAX_WEEKS_IN_ADVANCE}
            )
        return w


class PlaceUpdateSerializer(PlaceSerializer):
    class Meta:
        model = PlaceModel
        fields = PlaceSerializer.Meta.fields
        read_only_fields = PlaceSerializer.Meta.read_only_fields
        extra_kwargs = PlaceSerializer.Meta.extra_kwargs

    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance
        return super().save(**kwargs)

    @transaction.atomic()
    def update(self, place, validated_data):
        before_data = PlaceHistorySerializer(place).data
        place = super().update(place, validated_data)
        after_data = PlaceHistorySerializer(place).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.STORE_MODIFY,
                group=place.group,
                place=place,
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        place.group.refresh_active_status()
        return place


class PlaceSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceSubscription
        fields = [
            'place',
        ]

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)

    def validate_place(self, place):
        if place.placesubscription_set.filter(user=self.context['request'].user).exists():
            raise serializers.ValidationError(_('You are already subscribed to this place'))
        return place

    def create(self, validated_data):
        return PlaceSubscription.objects.create(**validated_data)
