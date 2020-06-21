from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet

from karrot.community_feed.models import CommunityFeedMeta
from karrot.community_feed.serializers import CommunityFeedMetaSerializer


class CommunityFeedViewSet(GenericViewSet):
    """
    Community Feed metadata
    """

    serializer_class = CommunityFeedMetaSerializer
    permission_classes = (IsAuthenticated,)

    def list(self, request, *args, **kwargs):
        meta, _ = CommunityFeedMeta.objects.get_or_create(user=request.user)
        serializer = CommunityFeedMetaSerializer(
            meta, context=self.get_serializer_context()
        )

        return Response(serializer.data)

    @action(detail=False, methods=["POST"])
    def mark_seen(self, request):
        """Mark community feed as seen"""
        self.check_permissions(request)
        meta, _ = CommunityFeedMeta.objects.update_or_create(
            {"marked_at": timezone.now()}, user=request.user
        )
        serializer = CommunityFeedMetaSerializer(meta)

        return Response(serializer.data)
