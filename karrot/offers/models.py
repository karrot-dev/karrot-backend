from enum import Enum
from django.db import models

from django.conf import settings
from django.db.models import IntegerField
from versatileimagefield.fields import VersatileImageField

from karrot.base.base_models import BaseModel
from karrot.conversations.models import ConversationMixin


class OfferStatus(Enum):
    ACTIVE = 'active'
    ACCEPTED = 'accepted'
    DISABLED = 'disabled'


class Offer(BaseModel, ConversationMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(blank=False, max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=False)
    status = models.CharField(
        default=OfferStatus.ACTIVE.value,
        choices=[(status.value, status.value) for status in OfferStatus],
        max_length=100,
    )


class OfferImage(BaseModel):
    class Meta:
        ordering = ['position']

    offer = models.ForeignKey(
        Offer,
        related_name='images',
        on_delete=models.CASCADE,
    )
    image = VersatileImageField(
        'Offer Image',
        upload_to='offer_images',
        null=False,
    )
    position = IntegerField(default=0)
