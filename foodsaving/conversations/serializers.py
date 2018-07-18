from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import DateTimeField

from foodsaving.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationParticipant,
    ConversationMessageReaction,
    ConversationThreadParticipant,
)
from foodsaving.conversations.helpers import normalize_emoji_name
from foodsaving.groups.models import Group


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
        messages = conversation.messages.exclude_replies()
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


class ConversationThreadNonParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = [
            'is_participant',
            'participants',
            'reply_count',
        ]

    is_participant = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

    def get_is_participant(self, thread):
        return False

    def get_participants(self, thread):
        return [participants.user_id for participants in thread.participants.all()]

    def get_reply_count(self, thread):
        return thread.replies_count


class ConversationThreadSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationThreadParticipant
        fields = [
            'is_participant',
            'participants',
            'reply_count',
            'seen_up_to',
            'muted',
            'unread_reply_count',
        ]

    is_participant = serializers.SerializerMethodField()
    participants = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    unread_reply_count = serializers.SerializerMethodField()

    def get_is_participant(self, participant):
        return True

    def get_participants(self, participant):
        return [participants.user_id for participants in participant.thread.participants.all()]

    def get_reply_count(self, participant):
        return participant.thread.replies_count

    def get_unread_reply_count(self, participant):
        return participant.thread.unread_replies_count

    def validate_seen_up_to(self, seen_up_to):
        if not self.instance.thread.thread_messages.filter(id=seen_up_to.id).exists():
            raise serializers.ValidationError('Must refer to a message in the thread')
        return seen_up_to

    def update(self, participant, validated_data):
        if 'seen_up_to' in validated_data:
            participant.seen_up_to = validated_data['seen_up_to']
        if 'muted' in validated_data:
            participant.muted = validated_data['muted']
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
            'updated_at',
            'reactions',
            'received_via',
            'is_editable',
            'thread',  # ideally would only be writable on create
            'thread_meta',
        ]
        read_only_fields = ('author', 'id', 'created_at', 'received_via', 'thread_meta',)

    thread_meta = serializers.SerializerMethodField()

    def get_thread_meta(self, message):
        if not message.is_first_in_thread():
            return None
        user = self.context['request'].user
        participant = message.participants.filter(user=user).first()
        if participant:
            return ConversationThreadSerializer(participant).data
        return ConversationThreadNonParticipantSerializer(message).data

    reactions = ConversationMessageReactionSerializer(many=True, read_only=True)
    is_editable = serializers.SerializerMethodField()

    def get_is_editable(self, message):
        return message.is_recent() and message.author == self.context['request'].user

    def validate_conversation(self, conversation):
        if self.context['request'].user not in conversation.participants.all():
            raise PermissionDenied(_('You are not in this conversation'))
        return conversation

    def validate(self, data):
        if 'thread' in data:
            thread = data['thread']
            conversation = data['conversation']

            # the thread must be in the correct conversation
            if thread.conversation.id != conversation.id:
                raise serializers.ValidationError(_('Thread is not in the same conversation'))

            # only some types of messages can have threads
            if not isinstance(data['conversation'].target, Group):
                raise serializers.ValidationError(_('You can only reply to Group messages'))

            # you cannot reply to replies
            if thread.is_thread_reply():
                raise serializers.ValidationError(_('You cannot reply to replies'))

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        return ConversationMessage.objects.create(author=user, **validated_data)
