from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import DateTimeField

from foodsaving.conversations.models import Conversation, ConversationMessage, \
    ConversationParticipant, ConversationMessageReaction
from foodsaving.conversations.helpers import normalize_emoji_name


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Conversation
        fields = [
            'id',
            'participants',
            'updated_at',
            'seen_up_to',
            'unread_message_count',
            'email_notifications'
        ]

    seen_up_to = serializers.SerializerMethodField()
    unread_message_count = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()
    email_notifications = serializers.SerializerMethodField()

    def validate(self, data):
        """Check the user is a participant"""
        conversation = self.instance
        if not self._participant(conversation):
            raise PermissionDenied(_('You are not in this conversation'))
        return data

    def get_seen_up_to(self, conversation):
        participant = self._participant(conversation)
        if not participant.seen_up_to:
            return None
        return participant.seen_up_to.id

    def get_unread_message_count(self, conversation):
        participant = self._participant(conversation)
        messages = conversation.messages
        if participant.seen_up_to:
            messages = messages.filter(id__gt=participant.seen_up_to.id)
        return messages.count()

    def get_updated_at(self, conversation):
        participant = self._participant(conversation)
        if participant.updated_at > conversation.updated_at:
            date = participant.updated_at
        else:
            date = conversation.updated_at
        return DateTimeField().to_representation(date)

    def get_email_notifications(self, conversation):
        return self._participant(conversation).email_notifications

    def _participant(self, conversation):
        user = self.context['request'].user
        if 'participant' not in self.context:
            self.context['participant'] = conversation.conversationparticipant_set.filter(user=user).first()
        return self.context['participant']


class ConversationMarkSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationParticipant
        fields = ('seen_up_to',)

    def validate_seen_up_to(self, message):
        if not self.instance.conversation.messages.filter(id=message.id).exists():
            raise serializers.ValidationError('Must refer to a message in the conversation')
        return message

    def update(self, participant, validated_data):
        participant.seen_up_to = validated_data['seen_up_to']
        participant.save()
        return participant


class ConversationEmailNotificationsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationParticipant
        fields = ('email_notifications',)


class EmojiField(serializers.Field):
    """Emoji field is normalized and validated here"""

    def to_representation(self, obj):
        return obj

    def to_internal_value(self, data):
        try:
            return normalize_emoji_name(data)
        except Exception:
            raise serializers.ValidationError('not a valid emoji name')


class ConversationMessageReactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessageReaction
        fields = ('user', 'name', 'message')
        extra_kwargs = {
            'message': {'write_only': True}
        }

    name = EmojiField()


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = [
            'id',
            'author',
            'content',
            'conversation',
            'created_at',
            'updated_at',
            'reactions',
            'received_via',
            'is_editable'
        ]
        read_only_fields = ('author', 'id', 'created_at', 'received_via')

    reactions = ConversationMessageReactionSerializer(many=True, read_only=True)
    is_editable = serializers.SerializerMethodField()

    def get_is_editable(self, message):
        return message.is_recent() and message.author == self.context['request'].user

    def validate_conversation(self, conversation):
        if self.context['request'].user not in conversation.participants.all():
            raise PermissionDenied(_('You are not in this conversation'))
        return conversation

    def create(self, validated_data):
        user = self.context['request'].user
        return ConversationMessage.objects.create(author=user, **validated_data)
