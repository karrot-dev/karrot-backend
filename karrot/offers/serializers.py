from django.utils.translation import ugettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from versatileimagefield.serializers import VersatileImageFieldSerializer

from karrot.offers.models import Offer, OfferImage


class OfferImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = OfferImage
        fields = (
            'id',
            'position',
            'image',
            'image_urls',
            '_removed',
        )

    id = serializers.IntegerField(required=False)
    _removed = serializers.BooleanField(required=False)

    image = VersatileImageFieldSerializer(
        sizes='offer_image',
        required=True,
        allow_null=False,
        write_only=True,
    )
    image_urls = VersatileImageFieldSerializer(
        sizes='offer_image',
        source='image',
        read_only=True,
    )


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
            'images',
        )
        read_only_fields = (
            'id',
            'created_at',
            'status',
            'user',
        )

    images = OfferImageSerializer(many=True)

    def save(self, **kwargs):
        return super().save(user=self.context['request'].user)

    def create(self, validated_data):
        images = validated_data.pop('images')
        offer = Offer.objects.create(**validated_data)
        for image in images:
            OfferImage.objects.create(offer=offer, **image)
        return offer

    def update(self, instance, validated_data):
        offer = instance
        images = validated_data.pop('images', None)
        if images:
            for image in images:
                pk = image.pop('id', None)
                if pk:
                    if image.get('_removed', False):
                        OfferImage.objects.filter(pk=pk).delete()
                    else:
                        OfferImage.objects.filter(pk=pk).update(**image)
                else:
                    OfferImage.objects.create(offer=offer, **image)
        return serializers.ModelSerializer.update(self, instance, validated_data)

    def validate_images(self, images):
        existing_image_count = self.instance.images.count() if self.instance else 0
        add_image_count = 0
        remove_image_count = 0
        for image in images:
            if image.get('_removed', False):
                remove_image_count += 1
            elif not image.get('id', False):
                add_image_count += 1
        resulting_image_count = existing_image_count + add_image_count - remove_image_count
        if resulting_image_count == 0:
            raise serializers.ValidationError(_('Must have at least one image'))
        return images

    def validate_group(self, group):
        if not group.is_member(self.context['request'].user):
            raise PermissionDenied(_('You are not a member of this group.'))
        return group
