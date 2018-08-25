from django.db.models import Q
from django_filters.rest_framework import FilterSet, BooleanFilter, ModelChoiceFilter

from foodsaving.conversations.models import (Conversation, ConversationMessage)
from foodsaving.groups.models import Group


def group_queryset(request):
    if request is None or request.user.is_anonymous:
        return Group.objects.none()

    return Group.objects.filter(members=request.user)


class ConversationsFilter(FilterSet):
    exclude_wall = BooleanFilter(
        method='filter_exclude_wall',
        help_text='Exclude group wall conversation',
    )
    group = ModelChoiceFilter(
        queryset=group_queryset,
        method='filter_by_group',
        help_text='Filter conversations by group, always include private messages',
    )

    class Meta:
        model = Conversation
        fields = ['exclude_wall', 'group']

    def filter_exclude_wall(self, qs, name, value):
        if value is True:
            return qs.exclude(target_type__model='group')
        return qs

    def filter_by_group(self, qs, name, value):
        return qs.filter(Q(group=value) | Q(is_private=True))


class ConversationMessageFilter(FilterSet):
    group = ModelChoiceFilter(queryset=group_queryset, method='filter_by_group')

    class Meta:
        model = ConversationMessage
        fields = [
            'conversation',
            'thread',
            'group',
        ]

    def filter_by_group(self, qs, name, value):
        group = value
        conversation = Conversation.objects.get_or_create_for_target(group)
        return qs.filter(conversation=conversation)
