from django.conf import settings
from rest_framework import serializers
from django.utils.translation import ugettext as _


def prevent_reserved_names(value):
    if value.lower() in settings.RESERVED_NAMES:
        raise serializers.ValidationError(_('%(value)s is a reserved name') % {'value': value})
