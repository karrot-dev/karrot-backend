from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from config.options import get_git_rev
from karrot.activities.models import ActivityType
from karrot.bootstrap.serializers import BootstrapSerializer, ConfigSerializer
from karrot.groups.models import Group
from karrot.places.models import Place
from karrot.status.helpers import status_data
from karrot.utils.geoip import geoip_is_available, get_client_ip, ip_to_city

BACKEND_REVISION = get_git_rev()


def get_config_data():
    return {
        'fcm': {
            'api_key': getattr(settings, 'FCM_CLIENT_API_KEY', None),
            'messaging_sender_id': getattr(settings, 'FCM_CLIENT_MESSAGING_SENDER_ID', None),
            'project_id': getattr(settings, 'FCM_CLIENT_PROJECT_ID', None),
            'app_id': getattr(settings, 'FCM_CLIENT_APP_ID', None),
        },
        'sentry': {
            'dsn': settings.SENTRY_CLIENT_DSN,
            'environment': settings.SENTRY_ENVIRONMENT,
        },
    }


class ConfigViewSet(GenericViewSet):
    serializer_class = ConfigSerializer  # for OpenAPI generation with drf-spectacular

    def list(self, request, *args, **kwargs):
        data = get_config_data()
        serializer = ConfigSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)


class BootstrapViewSet(GenericViewSet):
    serializer_class = BootstrapSerializer  # for OpenAPI generation with drf-spectacular

    def list(self, request, *args, **kwargs):
        fields = request.query_params.get('fields', 'server,config,geoip,user,groups').split(',')
        user = request.user

        data = {
            'server': {
                'revision': BACKEND_REVISION,
            } if 'server' in fields else None,
            'config': get_config_data() if 'config' in fields else None,
            'geoip': self.get_geoip(request) if 'geoip' in fields else None,
            'groups': self.get_groups(user) if 'groups' in fields else None,
        }

        if user.is_authenticated:
            data.update({
                'user': user if 'user' in fields else None,
                'places': self.get_places(user) if 'places' in fields else None,
                'users': self.get_users(user) if 'users' in fields else None,
                'status': self.get_status(user) if 'status' in fields else None,
                'activity_types': self.get_activity_types(user) if 'activity_types' in fields else None,
            })

        # only keep fields we want (others should be None anyway...)
        data = {key: val for key, val in data.items() if key in fields}
        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)

    @staticmethod
    def get_geoip(request):
        if geoip_is_available():
            client_ip = get_client_ip(request)
            if client_ip:
                city = ip_to_city(client_ip)
                if city:
                    return {
                        'lat': city.get('latitude', None),
                        'lng': city.get('longitude', None),
                        'country_code': city.get('country_code', None),
                        'timezone': city.get('time_zone', None),
                    }

    @staticmethod
    def get_groups(user):
        return Group.objects.annotate_member_count().annotate_is_user_member(user)

    @staticmethod
    def get_users(user):
        is_member_of_group = Q(groups__in=user.groups.all())

        is_self = Q(id=user.id)

        groups = user.groups.all()
        is_applicant_of_group = Q(application__group__in=groups)

        return get_user_model().objects \
            .active() \
            .filter(is_member_of_group | is_applicant_of_group | is_self) \
            .distinct()

    @staticmethod
    def get_status(user):
        return status_data(user)

    @staticmethod
    def get_places(user):
        return Place.objects.filter(group__members=user).prefetch_related('subscribers')

    @staticmethod
    def get_activity_types(user):
        return ActivityType.objects.filter(group__members=user)
