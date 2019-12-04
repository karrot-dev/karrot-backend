from rest_framework import serializers
from rest_framework.exceptions import ValidationError

MAX_STATS = 50


class StatsEntrySerializer(serializers.Serializer):
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


class StatsSerializer(serializers.Serializer):
    stats = StatsEntrySerializer(many=True)

    def validate_stats(self, stats):
        if len(stats) > MAX_STATS:
            raise ValidationError('You can only send up to {}'.format(MAX_STATS))
        return stats
