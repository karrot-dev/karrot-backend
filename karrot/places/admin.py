from django.contrib import admin

from karrot.places.models import Place


@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
    pass
