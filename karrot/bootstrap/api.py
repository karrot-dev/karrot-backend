from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Q
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.bootstrap.serializers import BootstrapSerializer
from karrot.groups.models import Group
from karrot.status.helpers import status_data
from karrot.utils.geoip import get_client_ip, ip_to_lat_lon


@dataclass
class BootstrapData:
    auth_user: Optional[dict]
    groups_info: Optional[list]
    geoip: Optional[dict]
    status: Optional[dict]
    users: Optional[list]


@dataclass
class GeoData:
    lat: float
    lng: float


class BootstrapViewSet(GenericViewSet):
    def list(self, request, *args, **kwargs):
        user = request.user
        geo = None

        if user.is_authenticated:
            status = status_data(user)

            is_member_of_group = Q(groups__in=user.groups.all())
            is_self = Q(id=user.id)
            groups = user.groups.all()
            is_applicant_of_group = Q(application__group__in=groups)
            users = get_user_model().objects.active().filter(is_member_of_group | is_applicant_of_group |
                                                             is_self).distinct()
        else:
            status = None
            users = None

        client_ip = get_client_ip(request)
        client_ip = '47.68.119.255'
        if client_ip:
            lat_lng = ip_to_lat_lon(client_ip)
            if lat_lng:
                geo = GeoData(*lat_lng)

        data = BootstrapData(
            auth_user=user if user.is_authenticated else None,
            groups_info=Group.objects.prefetch_related('members'),
            geoip=geo,
            status=status,
            users=users,
        )
        serializer = BootstrapSerializer(data, context=self.get_serializer_context())
        return Response(serializer.data)
