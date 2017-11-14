from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from foodsaving.conversations.models import Conversation, ConversationMessage, ConversationParticipant


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = [
            'id',
            'participants',
            'created_at',
            'seen_up_to'
        ]

    seen_up_to = serializers.SerializerMethodField()

    def get_seen_up_to(self, conversation):
        user = None
        if 'user' in self.context:
            user = self.context['user']
        elif 'request' in self.context:
            user = self.context['request'].user

        if not user:
            return None

        participant = conversation.conversationparticipant_set.get(user=user)
        return participant.seen_up_to.id


class ConversationParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationParticipant
        fields = [
            'seen_up_to'
        ]

    def validate_seen_up_to(self, message):
        if not self.instance.conversation.messages.filter(id=message.id).exists():
            raise serializers.ValidationError('Must refer to a message in the conversation')
        return message

    def update(self, participant, validated_data):
        participant.seen_up_to = validated_data['seen_up_to']
        participant.save()
        return participant


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = [
            'id',
            'author',
            'content',
            'conversation',
            'created_at',
            'seen',
        ]
        read_only_fields = ('author', 'id', 'created_at', 'seen')

    seen = serializers.SerializerMethodField()

    def get_seen(self, message):
        user = None
        if 'user' in self.context:
            user = self.context['user']
        elif 'request' in self.context:
            user = self.context['request'].user

        if not user:
            return None

        # TODO: make sure this is cached when using this serializer over a list of messages
        participant = message.conversation.conversationparticipant_set.get(user=user)
        if participant.seen_up_to:
            return message.id <= participant.seen_up_to_id
        else:
            return False

    def validate_conversation(self, conversation):
        if self.context['request'].user not in conversation.participants.all():
            raise PermissionDenied(_('You are not in this conversation'))
        return conversation

    def create(self, validated_data):
        user = self.context['request'].user
        return ConversationMessage.objects.create(author=user, **validated_data)
