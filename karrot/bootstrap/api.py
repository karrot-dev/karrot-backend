from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework import status
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
        'upload': {
            'max_size': settings.FILE_UPLOAD_MAX_SIZE,
        },
        'forum': {
            'banner_topic_id': settings.FORUM_BANNER_TOPIC_ID,
            'discussions_feed': settings.FORUM_DISCUSSIONS_FEED,
        },
    }


class ConfigViewSet(GenericViewSet):
    serializer_class = ConfigSerializer  # for OpenAPI generation with drf-spectacular

    def list(self, request, *args, **kwargs):
        data = get_config_data()
        serializer = ConfigSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)


class BootstrapDataHandlers:
    @staticmethod
    def server(request):
        return {
            'revision': BACKEND_REVISION,
        }

    @staticmethod
    def config(request):
        return get_config_data()

    @staticmethod
    def user(request):
        if not request.user.is_authenticated:
            return None
        return request.user

    @staticmethod
    def geoip(request):
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
    def groups(request):
        # anon is ok here
        return Group.objects.annotate_member_count().annotate_is_user_member(request.user)

    @staticmethod
    def users(request):
        user = request.user

        if not user.is_authenticated:
            return None

        is_member_of_group = Q(groups__in=user.groups.all())

        is_self = Q(id=user.id)

        groups = user.groups.all()
        is_applicant_of_group = Q(application__group__in=groups)

        return get_user_model().objects \
            .active() \
            .filter(is_member_of_group | is_applicant_of_group | is_self) \
            .distinct()

    @staticmethod
    def status(request):
        if not request.user.is_authenticated:
            return None
        return status_data(request.user)

    @staticmethod
    def places(request):
        if not request.user.is_authenticated:
            return None
        return Place.objects.filter(group__members=request.user).prefetch_related('subscribers')

    @staticmethod
    def activity_types(request):
        if not request.user.is_authenticated:
            return None
        return ActivityType.objects.filter(group__members=request.user)


class BootstrapViewSet(GenericViewSet):
    serializer_class = BootstrapSerializer  # for OpenAPI generation with drf-spectacular
    handlers = BootstrapDataHandlers()
    defaults = (
        'server',
        'config',
        'geoip',
        'user',
        'groups',
    )

    def list(self, request, *args, **kwargs):
        fields = request.query_params.get('fields').split(',') if 'fields' in request.query_params else self.defaults
        valid_fields = dir(self.handlers)

        invalid_fields = [field for field in fields if field not in valid_fields]
        if invalid_fields:
            return Response(status=status.HTTP_400_BAD_REQUEST, data=f"invalid fields [{','.join(invalid_fields)}]")

        data = {field: getattr(self.handlers, field)(request) for field in fields}
        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
