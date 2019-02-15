from django.contrib import admin

from karrot.notifications.models import Notification


@admin.register(Notification)
class NotificationsAdmin(admin.ModelAdmin):
    pass
