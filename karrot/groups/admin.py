from django.contrib import admin

from karrot.groups.models import Group


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    pass
