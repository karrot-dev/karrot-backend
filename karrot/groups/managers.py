from django.conf import settings
from django.db import models
from karrot.groups.models import GroupQuerySet

class GroupManager(models.Manager):
    def create(self, *args, **kwargs):
        if 'theme' not in kwargs:
            kwargs['theme'] = settings.GROUP_THEME_DEFAULT.value
        if 'status' not in kwargs:
            kwargs['status'] = settings.GROUP_STATUS_DEFAULT.value
        return super(GroupManager, self).create(*args, **kwargs)

    def get_queryset(self):
        return GroupQuerySet(self.model, using=self._db)

    def user_is_editor(self, user):
        return self.get_queryset().user_is_editor(user)

    def annotate_active_editors_count(self):
        return self.get_queryset().annotate_active_editors_count()

    def annotate_yesterdays_member_count(self):
        return self.get_queryset().annotate_yesterdays_member_count()


