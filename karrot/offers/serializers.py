from django.utils.translation import ugettext as _

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from karrot.offers.models import Offer


class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = (
            'id',
            'created_at',
            'user',
            'group',
            'name',
            'description',
            'status',
        )
        read_only_fields = ['id', 'created_at', 'user']

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        return group
