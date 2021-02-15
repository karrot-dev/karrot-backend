from django.conf import settings
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from config.options import get_git_rev
from karrot.bootstrap.serializers import BootstrapSerializer, ConfigSerializer
from karrot.groups.models import Group
from karrot.utils.geoip import geoip_is_available, get_client_ip, ip_to_city

BACKEND_REVISION = get_git_rev()


def get_config_data():
    fcm_client_config = {}

    for key in (
            'api_key',
            'messaging_sender_id',
            'project_id',
            'app_id',
    ):
        attr = f'FCM_CLIENT_{key.upper()}'
        fcm_client_config[key] = getattr(settings, attr) if hasattr(settings, attr) else None

    return {
        'fcm': fcm_client_config,
        'sentry': {
            'dsn': settings.SENTRY_CLIENT_DSN,
        },
    }


class ConfigViewSet(GenericViewSet):
    def list(self, request, *args, **kwargs):
        data = get_config_data()
        serializer = ConfigSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)


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
            'server': {
                'revision': BACKEND_REVISION,
            },
            'config': get_config_data(),
            'user': user if user.is_authenticated else None,
            'geoip': geo_data,
            'groups': Group.objects.prefetch_related('members'),
        }

        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
