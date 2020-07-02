from django.contrib import admin

from karrot.activities.models import ActivitySeries, Activity


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    pass


@admin.register(ActivitySeries)
class ActivitySeriesAdmin(admin.ModelAdmin):
    pass
