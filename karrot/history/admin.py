from django.contrib import admin

from karrot.history.models import History


@admin.register(History)
class HistoryAdmin(admin.ModelAdmin):
    pass
