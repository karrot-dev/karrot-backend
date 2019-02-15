from django.contrib import admin

from karrot.users.models import User


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    pass
