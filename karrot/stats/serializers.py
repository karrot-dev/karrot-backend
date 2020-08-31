from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from karrot.history.models import History
from karrot.places.models import Place

MAX_STATS = 50


class ActivityHistoryStatsSerializer(serializers.ModelSerializer):
    # using the values('place, 'group') in the query doesn't seem to fit nicely with DRF model serializer
    # so having to explicitly declare these fields here
    place = serializers.IntegerField()
    group = serializers.IntegerField()

    done_count = serializers.IntegerField()
    leave_count = serializers.IntegerField()
    leave_late_count = serializers.IntegerField()
    feedback_weight = serializers.FloatField()

    class Meta:
        model = History
        fields = [
            'place',
            'group',
            'done_count',
            'leave_count',
            'leave_late_count',
            'feedback_weight',
        ]


class PlaceStatsSerializer(serializers.ModelSerializer):
    activity_done_count = serializers.IntegerField()
    activity_leave_count = serializers.IntegerField()
    activity_leave_late_count = serializers.IntegerField()
    activity_feedback_weight = serializers.FloatField()

    class Meta:
        model = Place
        fields = [
            'id',
            'name',
            'group',
            'status',
            'activity_done_count',
            'activity_leave_count',
            'activity_leave_late_count',
            'activity_feedback_weight',
        ]


class FrontendStatsEntrySerializer(serializers.Serializer):
    # timings
    ms = serializers.IntegerField()
    ms_resources = serializers.IntegerField()

    # app state
    first_load = serializers.BooleanField()
    logged_in = serializers.BooleanField()
    group = serializers.IntegerField(allow_null=True)
    route_name = serializers.CharField()
    route_path = serializers.CharField()

    # device/build info
    mobile = serializers.BooleanField()
    app = serializers.BooleanField()
    browser = serializers.CharField()
    os = serializers.CharField()
    dev = serializers.BooleanField()


class FrontendStatsSerializer(serializers.Serializer):
    stats = FrontendStatsEntrySerializer(many=True)

    def validate_stats(self, stats):
        if len(stats) > MAX_STATS:
            raise ValidationError('You can only send up to {}'.format(MAX_STATS))
        return stats
