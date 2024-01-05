from django.conf import settings
from django.db import models
from django.db.models import IntegerField
from django.utils import timezone
from versatileimagefield.fields import VersatileImageField
from versatileimagefield.image_warmer import VersatileImageFieldWarmer

from karrot.base.base_models import BaseModel
from karrot.conversations.models import ConversationMixin


class Offer(BaseModel, ConversationMixin):
    group = models.ForeignKey("groups.Group", on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(blank=False, max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=False)
    archived_at = models.DateTimeField(null=True)

    @property
    def ended_at(self):
        return self.archived_at

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def archive(self):
        self.archived_at = timezone.now()
        self.save()


class OfferImage(BaseModel):
    class Meta:
        ordering = ["position"]

    offer = models.ForeignKey(
        Offer,
        related_name="images",
        on_delete=models.CASCADE,
    )
    image = VersatileImageField(
        "Offer Image",
        upload_to="offer_images",
        null=False,
    )
    position = IntegerField(default=0)


def create_offer_image_warmer(instance_or_queryset, *, verbose=False):
    return VersatileImageFieldWarmer(
        instance_or_queryset=instance_or_queryset,
        rendition_key_set="offer_image",
        image_attr="image",
        verbose=verbose,
    )
