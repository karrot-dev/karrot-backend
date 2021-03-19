from enum import Enum

from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _

from karrot.base.base_models import BaseModel, LocationModel, UpdatedAtMixin
from karrot.conversations.models import ConversationMixin


class PlaceStatusOld(Enum):
    CREATED = 'created'
    NEGOTIATING = 'negotiating'
    ACTIVE = 'active'
    DECLINED = 'declined'
    ARCHIVED = 'archived'


class PlaceStatusCategory(Enum):
    """
    Maybe this is too confusing! ... the status having a type! we have PlaceStatusType and PlaceTypeStatus :)
    Ah, I renamed it to PlaceStatusCategory to try and make it less confusing...

    The idea is that in the software we need to distinguish between how to handle these different statuses that the
    user creates. Inactive ones we might not show in menus by default, and inhibit notifications, etc..

    And archived we would hide entirely from certain areas.
    """
    INACTIVE = 'inactive'
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class PlaceStatus(BaseModel, UpdatedAtMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='place_statuses')
    name = models.CharField(max_length=80)
    name_is_translatable = models.BooleanField(default=True)
    colour = models.CharField(max_length=6)
    # hmm, I wonder whether to get rid of this and have it set per place, or allow override so have it both ways?
    has_activities = models.BooleanField(default=True)
    category = models.CharField(
        default=PlaceStatusCategory.ACTIVE.value,
        choices=[(status.value, status.value) for status in PlaceStatusCategory],
        max_length=100,
    )
    # seems a very UI-specific thing to be in the database, maybe it can have another name
    # it's about whether it's a kind of default/active/main kind of status, or a hidden/special one
    # there is also the archived state which seems even more special, as it doesn't show at all..
    # maybe I actually want to always have active/archived statuses? maybe that's what this is for... OR...
    # show_in_menu = models.BooleanField(default=True)
    # is_active = models.BooleanField(default=True)
    # ... this would be the next level hidden, used for the "archive" mode...
    # is_hidden = models.BooleanField(default=True)
    # is_archived = models.BooleanField(default=True) or maybe need a special one that the user cannot set...


class PlaceTypeStatus(Enum):
    ACTIVE = 'active'
    ARCHIVED = 'archived'


class PlaceType(BaseModel, UpdatedAtMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='place_types')
    name = models.CharField(max_length=80)
    name_is_translatable = models.BooleanField(default=True)
    icon = models.CharField(max_length=32)
    # default_place_status = models.ForeignKey(PlaceStatusNext, on_delete=models.CASCADE)
    status = models.CharField(
        default=PlaceTypeStatus.ACTIVE.value,
        choices=[(status.value, status.value) for status in PlaceTypeStatus],
        max_length=100,
    )

    class Meta:
        unique_together = ('group', 'name')

    def get_translated_name(self):
        # the translations are collected via activity_types.py
        return _(self.name) if self.name_is_translatable else self.name


class Place(BaseModel, LocationModel, ConversationMixin):
    class Meta:
        unique_together = ('group', 'name')

    DEFAULT_STATUS = PlaceStatusOld.CREATED.value

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='places')
    name = models.CharField(max_length=settings.NAME_MAX_LENGTH)
    description = models.TextField(blank=True)
    weeks_in_advance = models.PositiveIntegerField(default=4)
    status_old = models.CharField(max_length=20, default=DEFAULT_STATUS)

    status = models.ForeignKey(
        PlaceStatus,
        related_name='places',
        on_delete=models.CASCADE,
    )

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
        return self.status.category == 'active'

    @property
    def conversation_supports_threads(self):
        return True


class PlaceSubscription(BaseModel):
    class Meta:
        unique_together = ('place', 'user')

    place = models.ForeignKey(Place, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
