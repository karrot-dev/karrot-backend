from rest_framework import serializers

from karrot.community_feed.models import CommunityFeedMeta


class CommunityFeedMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunityFeedMeta
        fields = ["marked_at"]
