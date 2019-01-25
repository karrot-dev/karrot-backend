from django.conf import settings
from django.db import transaction
from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils.misc import find_changed
from foodsaving.stores.models import Store as StoreModel, StoreStatus, StoreSubscription


class StoreHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreModel
        fields = '__all__'


class StoreSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreModel
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
        choices=[status.value for status in StoreStatus], default=StoreModel.DEFAULT_STATUS
    )

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context['request'].user)

    def create(self, validated_data):
        store = super().create(validated_data)

        # TODO move into receiver
        History.objects.create(
            typus=HistoryTypus.STORE_CREATE,
            group=store.group,
            store=store,
            users=[
                self.context['request'].user,
            ],
            payload=self.initial_data,
            after=StoreHistorySerializer(store).data,
        )
        store.group.refresh_active_status()
        return store

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


class StoreUpdateSerializer(StoreSerializer):
    class Meta:
        model = StoreModel
        fields = StoreSerializer.Meta.fields
        read_only_fields = StoreSerializer.Meta.read_only_fields
        extra_kwargs = StoreSerializer.Meta.extra_kwargs

    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance
        return super().save(**kwargs)

    @transaction.atomic()
    def update(self, store, validated_data):
        before_data = StoreHistorySerializer(store).data
        store = super().update(store, validated_data)
        after_data = StoreHistorySerializer(store).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.STORE_MODIFY,
                group=store.group,
                store=store,
                users=[self.context['request'].user],
                payload={k: self.initial_data.get(k)
                         for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        store.group.refresh_active_status()
        return store


class StoreSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StoreSubscription
        fields = [
            'store',
        ]

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)

    def validate_store(self, store):
        if store.storesubscription_set.filter(user=self.context['request'].user).exists():
            raise serializers.ValidationError(_('You are already subscribed to this store'))
        return store

    def create(self, validated_data):
        return StoreSubscription.objects.create(**validated_data)
