from django.contrib import admin

from foodsaving.bells.models import Bell


@admin.register(Bell)
class BellsAdmin(admin.ModelAdmin):
    pass
