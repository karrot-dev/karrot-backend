from django.contrib import admin

from karrot.pickups.models import PickupDateSeries, PickupDate


@admin.register(PickupDate)
class PickupDateAdmin(admin.ModelAdmin):
    pass


@admin.register(PickupDateSeries)
class PickupDateSeriesAdmin(admin.ModelAdmin):
    pass
