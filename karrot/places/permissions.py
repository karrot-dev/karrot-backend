from rest_framework import permissions

from karrot.groups.models import Group


class TypeHasNoPlaces(permissions.BasePermission):
    message = 'You cannot delete a type which has places'

    def has_object_permission(self, request, view, obj):
        if view.action == 'destroy':
            return not obj.places.exists()
        return True


class CannotChangeGroup(permissions.BasePermission):
    message = 'You cannot change the group for a type'

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return 'group' not in request.data
        return True


class IsGroupEditor(permissions.BasePermission):
    message = 'You need to be a group editor'

    def has_permission(self, request, view):
        if view.action == 'create':
            group = Group.objects.filter(id=request.data['group'], members=request.user).first()
            return group.is_editor(request.user) if group else False
        return True

    def has_object_permission(self, request, view, obj):
        if view.action in ('partial_update', 'destroy'):
            return obj.group.is_editor(request.user)
        return True
