from rest_framework import serializers
from rest_framework.exceptions import ValidationError

MAX_STATS = 50


class StatsEntrySerializer(serializers.Serializer):
    first_load = serializers.BooleanField()
    logged_in = serializers.BooleanField()
    mobile = serializers.BooleanField()
    route = serializers.CharField()
    ms = serializers.IntegerField()


class StatsSerializer(serializers.Serializer):
    stats = StatsEntrySerializer(many=True)

    def validate_stats(self, stats):
        if len(stats) > MAX_STATS:
            raise ValidationError('You can only send up to {}'.format(MAX_STATS))
        return stats
