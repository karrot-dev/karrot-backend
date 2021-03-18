from django.conf import settings
from django.db import transaction
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from karrot.history.models import History, HistoryTypus
from karrot.places.models import Place as PlaceModel, PlaceSubscription, PlaceType
from karrot.utils.misc import find_changed


class PlaceTypeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceType
        fields = '__all__'


class PlaceTypeSerializer(serializers.ModelSerializer):
    updated_message = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = PlaceType
        fields = [
            'id',
            'name',
            'name_is_translatable',
            'icon',
            'status',
            'group',
            "created_at",
            'updated_at',
            'updated_message',
        ]
        read_only_fields = [
            'id',
            'created_at',
            'updated_at',
        ]

    def save(self, **kwargs):
        if not self.instance:
            return super().save(**kwargs)

        updated_message = self.validated_data.pop('updated_message', None)

        place_type = self.instance
        changed_data = find_changed(place_type, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        before_data = PlaceTypeHistorySerializer(place_type).data
        place_type = super().save(**kwargs)
        after_data = PlaceTypeHistorySerializer(place_type).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.PLACE_TYPE_MODIFY,
                group=place_type.group,
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in changed_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )
        return place_type

    def create(self, validated_data):
        place_type = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.PLACE_TYPE_CREATE,
            group=place_type.group,
            users=[self.context['request'].user],
            payload=self.initial_data,
            after=PlaceTypeHistorySerializer(place_type).data,
        )
        return place_type


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
            'is_subscribed',
            'subscribers',
            'place_type',
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
            'subscribers',
        ]

    # status = serializers.ChoiceField(
    #     choices=[status.value for status in PlaceStatusOld], default=PlaceModel.DEFAULT_STATUS
    # )
    is_subscribed = serializers.SerializerMethodField()

    def get_is_subscribed(self, place):
        return any(u == self.context['request'].user for u in place.subscribers.all())

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
