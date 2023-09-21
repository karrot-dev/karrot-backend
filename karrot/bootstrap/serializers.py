from rest_framework import serializers

from karrot.activities.serializers import ActivityTypeSerializer
from karrot.groups.serializers import GroupPreviewSerializer
from karrot.places.serializers import PlaceSerializer
from karrot.status.helpers import StatusSerializer
from karrot.userauth.serializers import AuthUserSerializer
from karrot.users.serializers import UserSerializer


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
    environment = serializers.CharField()


class UploadConfigSerializer(serializers.Serializer):
    max_size = serializers.IntegerField()


class ForumConfigSerializer(serializers.Serializer):
    banner_topic_id = serializers.IntegerField()
    discussions_feed = serializers.CharField()


class WebPushConfigSerializer(serializers.Serializer):
    vapid_public_key = serializers.CharField()


class ConfigSerializer(serializers.Serializer):
    fcm = FCMClientConfigSerializer()
    sentry = SentryClientConfigSerializer()
    upload = UploadConfigSerializer()
    forum = ForumConfigSerializer()
    feedback_possible_days = serializers.IntegerField()
    web_push = WebPushConfigSerializer()


class BootstrapSerializer(serializers.Serializer):
    # always available
    server = ServerInfoSerializer(required=False)
    config = ConfigSerializer(required=False)
    geoip = GeoSerializer(required=False)
    groups = GroupPreviewSerializer(many=True, required=False)

    # require authenticated user
    user = AuthUserSerializer(required=False)
    places = PlaceSerializer(many=True, required=False)
    users = UserSerializer(many=True, required=False)
    status = StatusSerializer(required=False)
    activity_types = ActivityTypeSerializer(many=True, required=False)
