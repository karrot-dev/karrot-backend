from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.bootstrap.serializers import BootstrapSerializer
from karrot.groups.models import Group
from karrot.utils.geoip import geoip_is_available, get_client_ip, ip_to_city


class BootstrapViewSet(GenericViewSet):
    def list(self, request, *args, **kwargs):
        user = request.user
        geo_data = None

        if geoip_is_available():
            client_ip = get_client_ip(request)
            if client_ip:
                city = ip_to_city(client_ip)
                if city:
                    geo_data = {
                        'lat': city.get('latitude', None),
                        'lng': city.get('longitude', None),
                        'country_code': city.get('country_code', None),
                        'timezone': city.get('time_zone', None),
                    }

        data = {
            'user': user if user.is_authenticated else None,
            'geoip': geo_data,
            'groups': Group.objects.prefetch_related('members'),
        }

        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
