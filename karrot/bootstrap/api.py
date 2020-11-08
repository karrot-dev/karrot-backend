from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.bootstrap.serializers import BootstrapSerializer
from karrot.groups.models import Group
from karrot.utils.geoip import get_client_ip, ip_to_lat_lon, geoip_is_available


class BootstrapViewSet(GenericViewSet):
    def list(self, request, *args, **kwargs):
        user = request.user
        geo_data = None

        if geoip_is_available():
            client_ip = get_client_ip(request)
            if client_ip:
                lat_lng = ip_to_lat_lon(client_ip)
                if lat_lng:
                    geo_data = {'lat': lat_lng[0], 'lng': lat_lng[1]}

        data = {
            'user': user if user.is_authenticated else None,
            'geoip': geo_data,
            'groups': Group.objects.prefetch_related('members'),
        }

        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
