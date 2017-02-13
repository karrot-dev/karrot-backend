from django.contrib import admin

from yunity.stores.models import Store, PickupDate, PickupDateSeries

admin.site.register(Store)
admin.site.register(PickupDate)
admin.site.register(PickupDateSeries)
