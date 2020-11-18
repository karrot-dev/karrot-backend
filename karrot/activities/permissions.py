from django.conf import settings
from rest_framework import permissions

from karrot.groups.models import Group
from karrot.places.models import Place


class IsUpcoming(permissions.BasePermission):
    message = 'The activity is in the past.'

    def has_object_permission(self, request, view, obj):
        # do allow GETs for activities in the past
        if request.method in permissions.SAFE_METHODS:
            return True
        else:
            return obj.is_upcoming()


class IsEmptyActivity(permissions.BasePermission):
    message = 'You can only delete empty activities.'

    def has_object_permission(self, request, view, obj):
        if view.action == 'destroy':
            return obj.is_empty()
        return True


class HasJoinedActivity(permissions.BasePermission):
    message = 'You have not joined this activity.'

    def has_object_permission(self, request, view, obj):
        return obj.is_participant(request.user)


class HasNotJoinedActivity(permissions.BasePermission):
    message = 'You have already joined this activity.'

    def has_object_permission(self, request, view, obj):
        return not obj.is_participant(request.user)


class IsNotFull(permissions.BasePermission):
    message = 'Activity is already full.'

    def has_object_permission(self, request, view, obj):
        return not obj.is_full()


class IsSameParticipant(permissions.BasePermission):
    message = 'This feedback is given by another user.'

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.given_by == request.user
        return True


class IsRecentActivity(permissions.BasePermission):
    message = 'You can\'t give feedback for activities more than {} days ago.'.format(settings.FEEDBACK_POSSIBLE_DAYS)

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.about.is_recent()
        return True


class IsGroupEditor(permissions.BasePermission):
    message = 'You need to be a group editor'

    def has_permission(self, request, view):
        if view.action == 'create':
            if 'group' in request.data:
                group = Group.objects.filter(id=request.data['group'], members=request.user).first()
                return group.is_editor(request.user) if group else False
            elif 'place' in request.data:
                place = Place.objects.filter(id=request.data['place'], group__members=request.user).first()
                return place.group.is_editor(request.user) if place else False
        return True

    def has_object_permission(self, request, view, obj):
        if view.action in ('partial_update', 'destroy'):
            # can be used for activity or activity type
            if hasattr(obj, 'group'):
                return obj.group.is_editor(request.user)
            elif hasattr(obj, 'place'):
                return obj.place.group.is_editor(request.user)
            else:
                raise Exception('Cannot check permission for {}'.format(type(obj)))
        return True


class TypeHasNoActivities(permissions.BasePermission):
    message = 'You cannot delete a type which has activities'

    def has_object_permission(self, request, view, obj):
        if view.action == 'destroy':
            return not obj.activities.exists()
        return True


class CannotChangeGroup(permissions.BasePermission):
    message = 'You cannot change the group for a type'

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return 'group' not in request.data
        return True
