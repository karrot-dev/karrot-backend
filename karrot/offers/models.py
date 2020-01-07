from enum import Enum

from django.conf import settings
from django.db import models
from django.db.models import IntegerField, DateTimeField
from django.utils import timezone
from versatileimagefield.fields import VersatileImageField

from karrot.base.base_models import BaseModel
from karrot.conversations.models import ConversationMixin


class OfferStatus(Enum):
    ACTIVE = 'active'
    ARCHIVED = 'archived'


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
    status_changed_at = DateTimeField(default=timezone.now)

    @property
    def ended_at(self):
        if self.status == OfferStatus.ACTIVE.value:
            return None
        return self.status_changed_at

    def archive(self):
        self.status = OfferStatus.ARCHIVED.value
        self.status_changed_at = timezone.now()
        self.save()


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
