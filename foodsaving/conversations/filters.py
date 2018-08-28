from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django_filters.rest_framework import FilterSet, ModelChoiceFilter, BooleanFilter

from foodsaving.applications.models import GroupApplication
from foodsaving.conversations.models import (Conversation, ConversationMessage)
from foodsaving.groups.models import Group
from foodsaving.pickups.models import PickupDate


def group_queryset(request):
    if request is None or request.user.is_anonymous:
        return Group.objects.none()

    return Group.objects.filter(members=request.user)


class ConversationsFilter(FilterSet):
    class Meta:
        model = Conversation
        fields = [
            'exclude_type_group',
            'exclude_type_pickup',
            'exclude_type_application',
            'exclude_type_private',
            'exclude_other_applications',
            'group',
        ]

    def filter_exclude_type(self, qs, name, value, model):
        if value is True:
            type = ContentType.objects.get_for_model(model)
            return qs.exclude(target_type=type)
        return qs

    exclude_type_group = BooleanFilter(
        method='filter_exclude_type_group',
        help_text='Exclude group wall conversation',
    )

    def filter_exclude_type_group(self, *args):
        return self.filter_exclude_type(*args, model=Group)

    exclude_type_pickup = BooleanFilter(
        method='filter_exclude_type_pickup',
        help_text='Exclude pickup conversations',
    )

    def filter_exclude_type_pickup(self, *args):
        return self.filter_exclude_type(*args, model=PickupDate)

    exclude_type_application = BooleanFilter(
        method='filter_exclude_type_application',
        help_text='Exclude application conversations',
    )

    def filter_exclude_type_application(self, *args):
        return self.filter_exclude_type(*args, model=GroupApplication)

    exclude_type_private = BooleanFilter(
        method='filter_exclude_type_private',
        help_text='Exclude private conversations',
    )

    def filter_exclude_type_private(self, qs, name, value):
        if value is True:
            return qs.exclude(is_private=True)
        return qs

    exclude_other_applications = BooleanFilter(
        method='filter_exclude_other_applications',
        help_text='Exclude applications from other people',
    )

    def filter_exclude_other_applications(self, qs, name, value):
        if value is True:
            type = ContentType.objects.get_for_model(GroupApplication)
            my_applications = GroupApplication.objects.filter(user=self.request.user).values_list('id', flat=True)

            return qs.filter(Q(target_id__in=my_applications, target_type=type) | ~Q(target_type=type))
        return qs

    group = ModelChoiceFilter(
        queryset=group_queryset,
        method='filter_by_group',
        help_text='Filter conversations by group, always include private messages',
    )

    def filter_by_group(self, qs, name, value):
        return qs.filter(Q(group=value) | Q(is_private=True))


class ConversationMessageFilter(FilterSet):
    class Meta:
        model = ConversationMessage
        fields = [
            'conversation',
            'thread',
            'group',
        ]

    group = ModelChoiceFilter(queryset=group_queryset, method='filter_by_group')

    def filter_by_group(self, qs, name, value):
        group = value
        conversation = Conversation.objects.get_or_create_for_target(group)
        return qs.filter(conversation=conversation)
