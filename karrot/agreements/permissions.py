from rest_framework import permissions


class IsGroupEditor(permissions.BasePermission):
    message = "You need to be a group editor"

    def has_object_permission(self, request, view, agreement):
        if view.action in ("partial_update", "destroy"):
            return agreement.group.is_editor(request.user)
        return True
