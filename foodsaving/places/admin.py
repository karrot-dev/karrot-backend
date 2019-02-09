from django.contrib import admin

from foodsaving.places.models import Place


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    pass
