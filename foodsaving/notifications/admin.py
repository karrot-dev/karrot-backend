from django.contrib import admin

from foodsaving.notifications.models import Notification


@admin.register(Notification)
class NotificationsAdmin(admin.ModelAdmin):
    pass
