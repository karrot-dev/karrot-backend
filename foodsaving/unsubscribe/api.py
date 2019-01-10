from django.contrib.auth import get_user_model
from django.utils.translation import ugettext as _
from rest_framework import views, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from foodsaving.conversations.models import ConversationMessage
from foodsaving.unsubscribe.utils import parse_token, unsubscribe_from_all_conversations_in_group, \
    unsubscribe_from_thread, unsubscribe_from_conversation


class UnsubscribeView(views.APIView):
    permission_classes = (AllowAny, )

    @staticmethod
    def post(request, token):
        """
        Receive unauthenticated but signed unsubscribe requests
        These are the things people can click in emails regardless of whether they are logged in
        """

        # TODO: make it return a generic "invalid token" error in most cases

        choice = request.data.get('choice', 'conversation')
        data = parse_token(token)
        user = get_user_model().objects.get(pk=data['u'])

        if choice == 'conversation':
            if 'c' not in data:
                raise ValidationError(_('Token does not specify a conversation'))
            conversation = user.conversation_set.get(pk=data['c'])
            unsubscribe_from_conversation(user, conversation)

        elif choice == 'thread':
            if 't' not in data:
                raise ValidationError(_('Token does not specify a thread'))
            thread = ConversationMessage.objects.only_threads_with_user(user).get(pk=data['t'])
            unsubscribe_from_thread(user, thread)

        elif choice == 'group':
            if 'g' not in data:
                raise ValidationError(_('Token does not specify a group'))
            group = user.groups.get(pk=data['g'])
            unsubscribe_from_all_conversations_in_group(user, group)

        else:
            raise ValidationError(_('Invalid unsubscribe choice.'))

        return Response(status=status.HTTP_200_OK, data={})
