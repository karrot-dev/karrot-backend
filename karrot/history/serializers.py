from django.utils.dateparse import parse_datetime
from rest_framework import serializers
from rest_framework.fields import SerializerMethodField
from rest_framework_csv.renderers import CSVRenderer

from karrot.history.models import History, HistoryTypus


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
            'pickup',
            'users',
            'pickup_date',
        ]

    pickup_date = serializers.SerializerMethodField()
    date = serializers.SerializerMethodField()
    users = serializers.SerializerMethodField()

    def get_pickup_date(self, history):
        if history.payload is None:
            return

        datestr = history.payload.get('date')
        if datestr is None:
            return

        group = history.group

        # TODO rewrite old history entries
        date = parse_datetime(datestr[0])

        # TODO rewrite to isoformat(timespec='seconds') once we are on Python 3.6+
        return date.astimezone(group.timezone).isoformat()

    def get_date(self, history):
        group = history.group

        # TODO rewrite to isoformat(timespec='seconds') once we are on Python 3.6+
        return history.date.astimezone(group.timezone).isoformat()

    def get_users(self, history):
        user_ids = [str(u.id) for u in history.users.all()]
        return ','.join(user_ids)


class HistoryExportRenderer(CSVRenderer):
    header = HistoryExportSerializer.Meta.fields
    labels = {
        'group': 'group_id',
        'users': 'user_ids',
        'place': 'place_id',
        'pickup': 'pickup_id',
        'typus': 'type',
    }
