from rest_framework import serializers

from karrot.groups.serializers import GroupPreviewSerializer
from karrot.userauth.serializers import AuthUserSerializer


class ServerInfoSerializer(serializers.Serializer):
    revision = serializers.CharField()


class GeoSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()
    country_code = serializers.CharField()
    timezone = serializers.CharField()


class FCMClientConfigSerializer(serializers.Serializer):
    api_key = serializers.CharField()
    messaging_sender_id = serializers.CharField()
    project_id = serializers.CharField()
    app_id = serializers.CharField()


class SentryClientConfigSerializer(serializers.Serializer):
    dsn = serializers.CharField()


class ConfigSerializer(serializers.Serializer):
    fcm = FCMClientConfigSerializer()
    sentry = SentryClientConfigSerializer()


class BootstrapSerializer(serializers.Serializer):
    server = ServerInfoSerializer()
    config = ConfigSerializer()
    user = AuthUserSerializer()
    geoip = GeoSerializer()
    groups = GroupPreviewSerializer(many=True)
