from django.conf import settings
from rest_framework import serializers
from django.utils.translation import gettext as _

from karrot.config.settings import USERNAME_RE


def prevent_reserved_names(value):
    if value.lower() in settings.RESERVED_NAMES:
        raise serializers.ValidationError(_('%(value)s is a reserved name') % {'value': value})


def username_validator(value):
    if not USERNAME_RE.fullmatch(value):
        raise serializers.ValidationError('username_invalid')
