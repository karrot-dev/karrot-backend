from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework_csv.renderers import CSVRenderer

from karrot.history.models import History, HistoryTypus
from karrot.utils.date_utils import csv_datetime


class HistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = History
        fields = [
            'id',
            'date',
            'typus',
            'group',
            'place',
            'users',
            'payload',
        ]

    typus = SerializerMethodField()

    def get_typus(self, obj):
        return HistoryTypus.name(obj.typus)


class HistoryExportSerializer(HistorySerializer):
    class Meta:
        model = History
        fields = [
            'id',
            'date',
            'typus',
            'group',
            'place',
            'activity',
            'users',
            'activity_date',
        ]

    activity_date = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()

    def get_activity_date(self, history):
        # Try to get start date of activity
        if history.payload is None:
            return

        dates = history.payload.get('date')
        if dates is None:
            # It might be very old or about something else than an activity
            return

        date = parse_datetime(dates[0])

        group = history.group

        return csv_datetime(date.astimezone(group.timezone))

    def get_date(self, history):
        group = history.group

        return csv_datetime(history.date.astimezone(group.timezone))

    def get_users(self, history):
        user_ids = [str(u.id) for u in history.users.all()]
        return ','.join(user_ids)


class HistoryExportRenderer(CSVRenderer):
    header = HistoryExportSerializer.Meta.fields
    labels = {
        'group': 'group_id',
        'users': 'user_ids',
        'place': 'place_id',
        'activity': 'activity_id',
        'typus': 'type',
    }
