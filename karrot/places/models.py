from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _

from karrot.base.base_models import BaseModel, LocationModel, UpdatedAtMixin
from karrot.conversations.models import ConversationMixin


class PlaceStatus(models.TextChoices):
    CREATED = 'created'
    NEGOTIATING = 'negotiating'
    ACTIVE = 'active'
    DECLINED = 'declined'
    ARCHIVED = 'archived'


class PlaceDefaultView(models.TextChoices):
    ACTIVITIES = 'activities'
    WALL = 'wall'


class PlaceTypeStatus(models.TextChoices):
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class PlaceType(BaseModel, UpdatedAtMixin):
    DEFAULT_STATUS = PlaceTypeStatus.ACTIVE.value

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='place_types')
    name = models.CharField(max_length=80)
    name_is_translatable = models.BooleanField(default=True)
    icon = models.CharField(max_length=100)
    status = models.CharField(
        choices=PlaceTypeStatus.choices,
        max_length=100,
        default=DEFAULT_STATUS,
    )
    archived_at = models.DateTimeField(null=True)

    class Meta:
        unique_together = ('group', 'name')

    def get_translated_name(self):
        # the translations are collected via place_types.py
        return _(self.name) if self.name_is_translatable else self.name


class Place(BaseModel, LocationModel, ConversationMixin):
    class Meta:
        unique_together = ('group', 'name')

    DEFAULT_STATUS = PlaceStatus.CREATED.value
    DEFAULT_DEFAULT_VIEW = PlaceDefaultView.ACTIVITIES.value

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='places')
    name = models.CharField(max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=True)
    weeks_in_advance = models.PositiveIntegerField(default=4)
    status = models.CharField(choices=PlaceStatus.choices, max_length=20, default=DEFAULT_STATUS)
    archived_at = models.DateTimeField(null=True)
    default_view = models.CharField(choices=PlaceDefaultView.choices, max_length=20, default=DEFAULT_DEFAULT_VIEW)

    place_type = models.ForeignKey(
        PlaceType,
        related_name='places',
        on_delete=models.CASCADE,
    )

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

    @property
    def conversation_supports_threads(self):
        return True


class PlaceSubscription(BaseModel):
    class Meta:
        unique_together = ('place', 'user')

    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
