from enum import Enum

from django.conf import settings
from django.db import models

from karrot.base.base_models import BaseModel, LocationModel
from karrot.conversations.models import ConversationMixin


class PlaceStatus(Enum):
    CREATED = 'created'
    NEGOTIATING = 'negotiating'
    ACTIVE = 'active'
    DECLINED = 'declined'
    ARCHIVED = 'archived'


class Place(BaseModel, LocationModel, ConversationMixin):
    class Meta:
        unique_together = ('group', 'name')

    DEFAULT_STATUS = PlaceStatus.CREATED.value

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='places')
    name = models.CharField(max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=True)
    weeks_in_advance = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, default=DEFAULT_STATUS)

    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='PlaceSubscription',
        related_name='places_subscribed',
    )
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return 'Place {} ({})'.format(self.name, self.group)

    def is_active(self):
        return self.status == 'active'


class PlaceSubscription(BaseModel):
    class Meta:
        unique_together = ('place', 'user')

    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
