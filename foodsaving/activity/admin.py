from django.contrib import admin

from foodsaving.activity.models import Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    pass
