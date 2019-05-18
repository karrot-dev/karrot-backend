from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.fields import DateTimeField

from karrot.conversations.helpers import normalize_emoji_name
from karrot.conversations.models import (
    ConversationMessage, ConversationParticipant, ConversationMessageReaction, ConversationThreadParticipant,
    ConversationMeta, ConversationNotificationStatus
)


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
        extra_kwargs = {'message': {'write_only': True}}

    name = EmojiField()


class ConversationThreadNonParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = [
            'is_participant',
            'participants',
            'reply_count',
        ]

    is_participant = serializers.ReadOnlyField(default=False)
    participants = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()

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

    is_participant = serializers.ReadOnlyField(default=True)
    participants = serializers.SerializerMethodField()
    reply_count = serializers.SerializerMethodField()
    unread_reply_count = serializers.SerializerMethodField()

    def get_participants(self, participant):
        return [participants.user_id for participants in participant.thread.participants.all()]

    def get_reply_count(self, participant):
        return participant.thread.replies_count

    def get_unread_reply_count(self, participant):
        count = getattr(participant.thread, 'unread_replies_count', None)
        if count is None:
            messages = participant.thread.thread_messages.only_replies()
            if participant.seen_up_to_id:
                messages = messages.filter(id__gt=participant.seen_up_to_id)
            return messages.count()
        return count

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
            'edited_at',
            'reactions',
            'received_via',
            'is_editable',
            'thread',  # ideally would only be writable on create
            'thread_meta',
        ]
        read_only_fields = (
            'author',
            'id',
            'created_at',
            'edited_at',
            'received_via',
            'thread_meta',
        )

    thread_meta = serializers.SerializerMethodField()

    def get_thread_meta(self, message):
        if not message.is_first_in_thread():
            return None
        user = self.context['request'].user
        # we are filtering in python to make use of prefetched data
        participant = next((p for p in message.participants.all() if p.user_id == user.id), None)
        if participant:
            return ConversationThreadSerializer(participant).data
        return ConversationThreadNonParticipantSerializer(message).data

    reactions = ConversationMessageReactionSerializer(many=True, read_only=True)
    is_editable = serializers.SerializerMethodField()

    def get_is_editable(self, message):
        return message.is_recent() and message.author_id == self.context['request'].user.id

    def validate_conversation(self, conversation):
        if not conversation.can_access(self.context['request'].user):
            raise PermissionDenied(_('You are not in this conversation'))
        if conversation.is_closed:
            raise PermissionDenied(_('This conversation has been closed'))
        return conversation

    def validate(self, data):
        if 'thread' in data:
            thread = data['thread']

            if 'view' in self.context and self.context['view'].action == 'partial_update':
                raise serializers.ValidationError('You cannot change the thread of a message')

            if 'conversation' in data:
                conversation = data['conversation']

                # the thread must be in the correct conversation
                if thread.conversation.id != conversation.id:
                    raise serializers.ValidationError('Thread is not in the same conversation')

                # only some types of messages can have threads
                if conversation.type() not in ('group', 'place'):
                    raise serializers.ValidationError('You can only reply to wall messages')

            # you cannot reply to replies
            if thread.is_thread_reply():
                raise serializers.ValidationError('You cannot reply to replies')

        return data

    def create(self, validated_data):
        user = self.context['request'].user
        return ConversationMessage.objects.create(author=user, **validated_data)


class ConversationSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationParticipant
        fields = [
            'id',
            'participants',
            'group',
            'updated_at',
            'type',
            'target_id',
            'is_closed',
            'seen_up_to',
            'unread_message_count',
            'notifications',
        ]

    id = serializers.IntegerField(source='conversation.id', read_only=True)
    participants = serializers.PrimaryKeyRelatedField(source='conversation.participants', many=True, read_only=True)
    group = serializers.PrimaryKeyRelatedField(source='conversation.group', read_only=True)
    type = serializers.CharField(source='conversation.type', read_only=True)
    target_id = serializers.IntegerField(source='conversation.target_id', read_only=True)
    is_closed = serializers.BooleanField(source='conversation.is_closed', read_only=True)
    notifications = serializers.ChoiceField(choices=[(c.value, c.value) for c in ConversationNotificationStatus])

    unread_message_count = serializers.SerializerMethodField()
    updated_at = serializers.SerializerMethodField()

    def get_unread_message_count(self, participant):
        annotated = getattr(participant, 'unread_message_count', None)
        if annotated is not None:
            return annotated
        messages = participant.conversation.messages.exclude_replies()
        if participant.seen_up_to_id:
            messages = messages.filter(id__gt=participant.seen_up_to_id)
        return messages.count()

    def get_updated_at(self, participant):
        if participant.updated_at > participant.conversation.updated_at:
            date = participant.updated_at
        else:
            date = participant.conversation.updated_at
        return DateTimeField().to_representation(date)

    def validate_seen_up_to(self, message):
        if not self.instance.conversation.messages.filter(id=message.id).exists():
            raise serializers.ValidationError('Must refer to a message in the conversation')
        return message

    def validate_notifications(self, notifications):
        participant = self.instance
        if (participant and notifications == ConversationNotificationStatus.NONE.value
                and participant.conversation.is_private):
            raise serializers.ValidationError('You cannot leave a private conversation')
        if (participant and notifications == ConversationNotificationStatus.NONE.value
                and not participant.conversation.is_group_public):
            # We currently don't support unsubscribing from non group-public conversation
            # TODO figure out a good solution how to handle this case, then remove this restriction
            raise serializers.ValidationError('You cannot leave a conversation that is not group public')
        return notifications

    def update(self, participant, validated_data):
        notifications = validated_data.get('notifications', None)
        if notifications == ConversationNotificationStatus.NONE.value:
            if participant.id is not None:
                # delete participant
                participant.delete()
            return participant
        elif notifications == ConversationNotificationStatus.MUTED.value:
            participant.muted = True
        elif notifications == ConversationNotificationStatus.ALL.value:
            participant.muted = False

        if 'seen_up_to' in validated_data:
            participant.seen_up_to = validated_data['seen_up_to']
        participant.save()
        return participant


class ConversationMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMeta
        fields = ['conversations_marked_at', 'threads_marked_at']
