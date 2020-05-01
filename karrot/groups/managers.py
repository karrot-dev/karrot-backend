from django.conf import settings
from django.db import models

class GroupManager(models.Manager):
    def create(self, *args, **kwargs):
        if 'theme' not in kwargs:
            kwargs['theme'] = settings.GROUP_THEME_DEFAULT.value
        if 'status' not in kwargs:
            kwargs['status'] = settings.GROUP_STATUS_DEFAULT.value
        return super(GroupManager, self).create(*args, **kwargs)

