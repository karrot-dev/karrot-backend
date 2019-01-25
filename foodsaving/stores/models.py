from enum import Enum

from django.conf import settings
from django.db import models

from foodsaving.base.base_models import BaseModel, LocationModel
from foodsaving.conversations.models import ConversationMixin


class StoreStatus(Enum):
    CREATED = 'created'
    NEGOTIATING = 'negotiating'
    ACTIVE = 'active'
    DECLINED = 'declined'
    ARCHIVED = 'archived'


class Store(BaseModel, LocationModel, ConversationMixin):
    class Meta:
        unique_together = ('group', 'name')

    DEFAULT_STATUS = StoreStatus.CREATED.value

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='stores')
    name = models.CharField(max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=True)
    weeks_in_advance = models.PositiveIntegerField(default=4)
    status = models.CharField(max_length=20, default=DEFAULT_STATUS)

    subscribers = models.ManyToManyField(
        settings.AUTH_USER_MODEL,
        through='StoreSubscription',
        related_name='stores_subscribed',
    )
    last_changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
    )

    def __str__(self):
        return 'Store {} ({})'.format(self.name, self.group)

    def is_active(self):
        return self.status == 'active'


class StoreSubscription(BaseModel):
    class Meta:
        unique_together = ('store', 'user')

    store = models.ForeignKey(Store, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
