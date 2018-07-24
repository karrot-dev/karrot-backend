from django.db import models
from django.conf import settings

from foodsaving.base.base_models import BaseModel


class Trust(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trust')
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    given_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='trust_given')

    class Meta:
        unique_together = (('user', 'group', 'given_by'),)
