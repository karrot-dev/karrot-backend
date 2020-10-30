from rest_framework import serializers

from karrot.groups.serializers import GroupPreviewSerializer
from karrot.status.helpers import StatusSerializer
from karrot.userauth.serializers import AuthUserSerializer
from karrot.users.serializers import UserSerializer


class GeoSerializer(serializers.Serializer):
    lat = serializers.FloatField()
    lng = serializers.FloatField()


class BootstrapSerializer(serializers.Serializer):
    auth_user = AuthUserSerializer()
    geoip = GeoSerializer()
    users = UserSerializer(many=True)
    status = StatusSerializer()
    groups_info = GroupPreviewSerializer(many=True)
