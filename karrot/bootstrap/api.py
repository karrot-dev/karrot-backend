from dataclasses import dataclass
from typing import Optional

from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.bootstrap.serializers import BootstrapSerializer
from karrot.groups.models import Group
from karrot.utils.geoip import get_client_ip, ip_to_lat_lon, geoip_is_available


@dataclass
class BootstrapData:
    user: Optional[dict]
    geoip: Optional[dict]
    groups: Optional[list]


@dataclass
class GeoData:
    lat: float
    lng: float


class BootstrapViewSet(GenericViewSet):
    def list(self, request, *args, **kwargs):
        user = request.user
        geo_data = None

        if geoip_is_available():
            client_ip = get_client_ip(request)
            if client_ip:
                lat_lng = ip_to_lat_lon(client_ip)
                if lat_lng:
                    geo_data = GeoData(*lat_lng)

        data = BootstrapData(
            user=user if user.is_authenticated else None,
            geoip=geo_data,
            groups=Group.objects.prefetch_related('members'),
        )

        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
