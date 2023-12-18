from typing import Optional

from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework_csv.renderers import CSVRenderer

from karrot.history.models import History, HistoryTypus
from karrot.utils.date_utils import csv_datetime


class HistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = History
        fields = [
            "id",
            "date",
            "typus",
            "group",
            "place",
            "agreement",
            "users",
            "payload",
            "message",
            "after",
            "changes",
        ]

    typus = SerializerMethodField()
    after = SerializerMethodField()

    changes = SerializerMethodField()

    def get_changes(self, obj) -> Optional[dict]:
        if obj.typus == HistoryTypus.AGREEMENT_MODIFY:
            changes = {}
            for k in (
                "title",
                "summary",
                "content",
            ):
                if obj.before[k] != obj.after[k]:
                    changes[k] = {
                        "before": obj.before[k],
                        "after": obj.after[k],
                    }
            if changes:
                return changes
        return None

    def get_typus(self, obj) -> str:
        return HistoryTypus.name(obj.typus)

    def get_after(self, obj) -> Optional[dict]:
        # It's limited to these types as if we just generally return it we might send
        # internal/private data back to the client. This is a bit of technical debt as
        # we should rethink the history data a bit to ensure we always have what we need.
        return (
            obj.after
            if obj.typus
            in (
                HistoryTypus.ACTIVITY_TYPE_CREATE,
                HistoryTypus.ACTIVITY_TYPE_MODIFY,
            )
            else None
        )


class HistoryExportSerializer(HistorySerializer):
    class Meta:
        model = History
        fields = [
            "id",
            "date",
            "typus",
            "group",
            "place",
            "activity",
            "users",
            "activity_date",
            "message",
        ]

    activity_date = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_activity_date(self, history):
        # Try to get start date of activity
        if history.payload is None:
            return

        dates = history.payload.get("date")
        if dates is None:
            # It might be very old or about something else than an activity
            return

        date = parse_datetime(dates[0])

        group = history.group

        return csv_datetime(date.astimezone(group.timezone))

    @extend_schema_field(OpenApiTypes.DATETIME)
    def get_date(self, history):
        group = history.group

        return csv_datetime(history.date.astimezone(group.timezone))

    @extend_schema_field(OpenApiTypes.STR)
    def get_users(self, history):
        user_ids = [str(u.id) for u in history.users.all()]
        return ",".join(user_ids)


class HistoryExportRenderer(CSVRenderer):
    header = HistoryExportSerializer.Meta.fields
    labels = {
        "group": "group_id",
        "users": "user_ids",
        "place": "place_id",
        "activity": "activity_id",
        "typus": "type",
    }
