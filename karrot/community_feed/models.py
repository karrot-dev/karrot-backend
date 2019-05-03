from django.conf import settings
from django.db import models

from karrot.base.base_models import BaseModel


class CommunityFeedMeta(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(null=True)
