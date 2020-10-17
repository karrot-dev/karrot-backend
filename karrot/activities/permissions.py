from django.conf import settings
from rest_framework import permissions
from django.utils.translation import gettext_lazy as _


class IsUpcoming(permissions.BasePermission):
    message = _('The activity is in the past.')

    def has_object_permission(self, request, view, obj):
        # do allow GETs for activities in the past
        if request.method in permissions.SAFE_METHODS:
            return True
        else:
            return obj.is_upcoming()


class IsEmptyActivity(permissions.BasePermission):
    message = _('You can only delete empty activities.')

    def has_object_permission(self, request, view, obj):
        if view.action == 'destroy':
            return obj.is_empty()
        return True


class HasJoinedActivity(permissions.BasePermission):
    message = _('You have not joined this activity.')

    def has_object_permission(self, request, view, obj):
        return obj.is_participant(request.user)


class HasNotJoinedActivity(permissions.BasePermission):
    message = _('You have already joined this activity.')

    def has_object_permission(self, request, view, obj):
        return not obj.is_participant(request.user)


class IsNotFull(permissions.BasePermission):
    message = _('Activity is already full.')

    def has_object_permission(self, request, view, obj):
        return not obj.is_full()


class IsSameParticipant(permissions.BasePermission):
    message = _('This feedback is given by another user.')

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.given_by == request.user
        return True


class IsRecentActivity(permissions.BasePermission):
    message = _('You can\'t give feedback for activities more than %(days_number)s days ago.') % \
        {'days_number': settings.FEEDBACK_POSSIBLE_DAYS}

    def has_object_permission(self, request, view, obj):
        if view.action == 'partial_update':
            return obj.about.is_recent()
        return True


class IsGroupEditor(permissions.BasePermission):
    message = _('You need to be a group editor')

    def has_object_permission(self, request, view, obj):
        if view.action in ('partial_update', 'destroy'):
            return obj.place.group.is_editor(request.user)
        return True
