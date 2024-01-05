from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from karrot.groups.serializers import GroupPreviewSerializer
from karrot.history.models import History, HistoryTypus
from karrot.places.models import Place as PlaceModel
from karrot.places.models import PlaceStatus, PlaceSubscription, PlaceType
from karrot.utils.misc import find_changed


class PlaceTypeHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceType
        fields = "__all__"


class PlaceStatusHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceStatus
        fields = "__all__"


class PlaceTypeSerializer(serializers.ModelSerializer):
    is_archived = serializers.BooleanField(default=False)
    updated_message = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = PlaceType
        fields = [
            "id",
            "name",
            "name_is_translatable",
            "description",
            "icon",
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
                users=[self.context["request"].user],
                payload={k: self.initial_data.get(k) for k in changed_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )
        return place_type

    def create(self, validated_data):
        if "is_archived" in validated_data:
            # can't create something in an archived state
            validated_data.pop("is_archived")
        place_type = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.PLACE_TYPE_CREATE,
            group=place_type.group,
            users=[self.context["request"].user],
            payload=self.initial_data,
            after=PlaceTypeHistorySerializer(place_type).data,
        )
        return place_type


class PlaceStatusSerializer(serializers.ModelSerializer):
    is_archived = serializers.BooleanField(default=False)
    updated_message = serializers.CharField(write_only=True, required=False)
    set_places_to_status = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = PlaceStatus
        fields = [
            "id",
            "name",
            "name_is_translatable",
            "description",
            "colour",
            "order",
            "is_visible",
            "archived_at",
            "is_archived",
            "group",
            "created_at",
            "updated_at",
            "updated_message",
            "set_places_to_status",
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

    def validate_set_places_to_status(self, status_id):
        group = self.instance.group
        if not group.place_statuses.filter(id=status_id).exists():
            raise PermissionDenied("Invalid status")
        return status_id

    def save(self, **kwargs):
        if not self.instance:
            return super().save(**kwargs)

        updated_message = self.validated_data.pop("updated_message", None)
        set_places_to_status = self.validated_data.pop("set_places_to_status", None)

        place_status = self.instance
        changed_data = find_changed(place_status, self.validated_data)
        self._validated_data = changed_data
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        if "is_archived" in self.validated_data:
            is_archived = self.validated_data.pop("is_archived")
            archived_at = timezone.now() if is_archived else None
            self.initial_data["archived_at"] = self.validated_data["archived_at"] = archived_at

        before_data = PlaceStatusHistorySerializer(place_status).data
        status = super().save(**kwargs)
        after_data = PlaceStatusHistorySerializer(place_status).data

        if set_places_to_status:
            # update any places if needed
            # do it in a loop, so we trigger signals
            for place in PlaceModel.objects.filter(status=status):
                place.status_id = set_places_to_status
                place.save()

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.PLACE_STATUS_MODIFY,
                group=status.group,
                users=[self.context["request"].user],
                payload={k: self.initial_data.get(k) for k in changed_data.keys()},
                before=before_data,
                after=after_data,
                message=updated_message,
            )
        return status

    def create(self, validated_data):
        if "is_archived" in validated_data:
            # can't create something in an archived state
            validated_data.pop("is_archived")
        status = super().create(validated_data)
        History.objects.create(
            typus=HistoryTypus.PLACE_STATUS_CREATE,
            group=status.group,
            users=[self.context["request"].user],
            payload=self.initial_data,
            after=PlaceStatusHistorySerializer(status).data,
        )
        return status


class PlaceHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceModel
        fields = "__all__"


class PublicPlaceSerializer(serializers.ModelSerializer):
    group = GroupPreviewSerializer()
    place_type = PlaceTypeSerializer()

    class Meta:
        model = PlaceModel
        fields = [
            "place_type",
            "name",
            "group",
            "address",
            "latitude",
            "longitude",
        ]
        read_only_fields = fields


class PlaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceModel
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
            "is_subscribed",
            "subscribers",
            "place_type",
            "default_view",
        ]
        extra_kwargs = {
            "name": {
                "min_length": 3,
            },
            "description": {
                "trim_whitespace": False,
                "max_length": settings.DESCRIPTION_MAX_LENGTH,
            },
            "place_type": {
                "required": False,
            },
        }
        read_only_fields = [
            "id",
            "subscribers",
            "archived_at",
        ]

    is_subscribed = serializers.SerializerMethodField()

    def get_is_subscribed(self, place) -> bool:
        return any(u == self.context["request"].user for u in place.subscribers.all())

    def save(self, **kwargs):
        return super().save(last_changed_by=self.context["request"].user)

    def create(self, validated_data):
        place = super().create(validated_data)

        # TODO move into receiver
        History.objects.create(
            typus=HistoryTypus.STORE_CREATE,
            group=place.group,
            place=place,
            users=[
                self.context["request"].user,
            ],
            payload=self.initial_data,
            after=PlaceHistorySerializer(place).data,
        )
        place.group.refresh_active_status()
        return place

    def validate(self, attrs):
        if not self.instance and not attrs.get("place_type"):
            """creating place without place type, we'll provide a default"""
            group = attrs.get("group")
            attrs["place_type"] = group.place_types.get(name="Unspecified")
        return attrs

    def validate_group(self, group):
        if not group.is_member(self.context["request"].user):
            raise PermissionDenied("You are not a member of this group.")
        if not group.is_editor(self.context["request"].user):
            raise PermissionDenied("You need to be a group editor")
        return group

    def validate_weeks_in_advance(self, w):
        if w < 1:
            raise serializers.ValidationError(_("Set at least one week in advance"))
        if w > settings.STORE_MAX_WEEKS_IN_ADVANCE:
            raise serializers.ValidationError(
                _("Do not set more than %(count)s weeks in advance") % {"count": settings.STORE_MAX_WEEKS_IN_ADVANCE}
            )
        return w


class PlaceUpdateSerializer(PlaceSerializer):
    is_archived = serializers.BooleanField(default=False)

    class Meta:
        model = PlaceModel
        fields = PlaceSerializer.Meta.fields
        read_only_fields = PlaceSerializer.Meta.read_only_fields
        extra_kwargs = PlaceSerializer.Meta.extra_kwargs

    @transaction.atomic()
    def save(self, **kwargs):
        self._validated_data = find_changed(self.instance, self.validated_data)
        skip_update = len(self.validated_data.keys()) == 0
        if skip_update:
            return self.instance

        if "is_archived" in self.validated_data:
            is_archived = self.validated_data.pop("is_archived")
            archived_at = timezone.now() if is_archived else None
            self.initial_data["archived_at"] = self.validated_data["archived_at"] = archived_at

        return super().save(**kwargs)

    def update(self, place, validated_data):
        before_data = PlaceHistorySerializer(place).data
        place = super().update(place, validated_data)
        after_data = PlaceHistorySerializer(place).data

        if before_data != after_data:
            History.objects.create(
                typus=HistoryTypus.STORE_MODIFY,
                group=place.group,
                place=place,
                users=[self.context["request"].user],
                payload={k: self.initial_data.get(k) for k in validated_data.keys()},
                before=before_data,
                after=after_data,
            )
        place.group.refresh_active_status()
        return place


class PlaceSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlaceSubscription
        fields = [
            "place",
        ]

    def save(self, **kwargs):
        return super().save(user=self.context["request"].user)

    def validate_place(self, place):
        if place.placesubscription_set.filter(user=self.context["request"].user).exists():
            raise serializers.ValidationError(_("You are already subscribed to this place"))
        return place

    def create(self, validated_data):
        return PlaceSubscription.objects.create(**validated_data)
