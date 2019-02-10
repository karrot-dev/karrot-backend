from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import ForeignKey, TextField, ManyToManyField, BooleanField, CharField, QuerySet, Count, F, Q, \
    DateTimeField
from django.db.models.manager import BaseManager
from django.utils import timezone
from enum import Enum

from foodsaving.base.base_models import BaseModel, UpdatedAtMixin
from foodsaving.utils import markdown


class ConversationQuerySet(models.QuerySet):
    def create(self, **kwargs):
        target = kwargs.get('target', None)
        if target is not None:
            kwargs['is_group_public'] = target.conversation_is_group_public
            kwargs['group'] = target.group

        return super().create(**kwargs)

    def get_for_target(self, target):
        return self.filter_for_target(target).first()

    def get_or_create_for_target(self, target):
        return self.get_for_target(target) or self.create(target=target)

    def get_or_create_for_two_users(self, user1, user2):
        if user1.id == user2.id:
            raise Exception('Users need to be different')
        conv = self.filter(is_private=True, participants=user1) \
            .filter(participants=user2) \
            .first()
        if not conv:
            conv = self.create(is_private=True)
            conv.sync_users([user1, user2])
        return conv

    def filter_for_target(self, target):
        return self.filter(
            target_id=target.id,
            target_type=ContentType.objects.get_for_model(target),
        )

    def with_access(self, user):
        return self.filter(Q(participants=user) |
                           Q(group__groupmembership__user=user, is_group_public=True)).distinct()


class Conversation(BaseModel, UpdatedAtMixin):
    """A conversation between one or more users."""

    class Meta:
        unique_together = ('target_type', 'target_id')

    objects = ConversationQuerySet.as_manager()

    participants = ManyToManyField(settings.AUTH_USER_MODEL, through='ConversationParticipant')
    is_private = models.BooleanField(default=False)
    is_closed = models.BooleanField(default=False)

    # conversation belongs to this group
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, null=True)
    # can any group member access this conversation?
    is_group_public = models.BooleanField(default=False)

    target_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    target_id = models.PositiveIntegerField(null=True)
    target = GenericForeignKey('target_type', 'target_id')

    latest_message = models.ForeignKey(
        'conversations.ConversationMessage',
        on_delete=models.SET_NULL,
        null=True,
        related_name='conversation_latest_message'
    )

    def make_participant(self, **kwargs):
        defaults = {
            'updated_at': self.updated_at,
        }
        defaults.update(kwargs)
        return ConversationParticipant(conversation=self, **defaults)

    def join(self, user, **kwargs):
        participant = self.conversationparticipant_set.filter(user=user).first()
        if participant is None:
            participant = self.make_participant(user=user, **kwargs)
            participant.save()
        return participant

    def leave(self, user):
        self.conversationparticipant_set.filter(user=user).delete()

    def sync_users(self, desired_users):
        """Pass in a set of users and we ensure the Conversation will end up with the right participants."""
        existing_users = self.participants.all()
        for user in desired_users:
            if user not in existing_users:
                self.join(user)
        for user in existing_users:
            if user not in desired_users:
                self.leave(user)

    def can_access(self, user):
        if self.conversationparticipant_set.filter(user=user).exists():
            return True
        if self.is_group_public and self.group.is_member(user):
            return True
        return False

    def type(self):
        if self.is_private:
            return 'private'
        if self.target_type_id is None:
            return None

        type = str(self.target_type)
        if type == 'pickup date':
            return 'pickup'
        if type == 'group application':
            return 'application'

        return type

    def find_group(self):
        if self.is_private or self.target_type_id is None:
            return None
        return self.target.group


class ConversationMeta(BaseModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    marked_at = models.DateTimeField(null=True)


class ConversationParticipantQuerySet(QuerySet):
    def annotate_unread_message_count(self):
        exclude_replies = (
            Q(conversation__messages__thread_id=None) |
            Q(conversation__messages__id=F('conversation__messages__thread_id'))
        )
        unread_messages = Q(seen_up_to=None) | Q(conversation__messages__id__gt=F('seen_up_to'))
        filter = unread_messages & exclude_replies
        return self.annotate(unread_message_count=Count('conversation__messages', filter=filter, distinct=True))


class ConversationNotificationStatus(Enum):
    ALL = 'all'
    MUTED = 'muted'
    NONE = 'none'


class ConversationParticipant(BaseModel, UpdatedAtMixin):
    """The join table between Conversation and User."""

    objects = ConversationParticipantQuerySet.as_manager()

    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = ForeignKey(Conversation, on_delete=models.CASCADE)
    seen_up_to = ForeignKey(
        'ConversationMessage',
        null=True,
        on_delete=models.SET_NULL,
        related_name='conversationparticipants_seen_up_to',
    )
    notified_up_to = ForeignKey(
        'ConversationMessage',
        null=True,
        on_delete=models.SET_NULL,
        related_name='conversationparticipants_notified_up_to',
    )
    muted = BooleanField(default=False)

    @property
    def notifications(self):
        if self.id is None:
            # participant does not exist in database
            return ConversationNotificationStatus.NONE.value
        if self.muted:
            return ConversationNotificationStatus.MUTED.value
        return ConversationNotificationStatus.ALL.value

    def unseen_and_unnotified_messages(self):
        messages = self.conversation.messages.exclude_replies()
        if self.seen_up_to_id is not None:
            messages = messages.filter(id__gt=self.seen_up_to_id)
        if self.notified_up_to_id is not None:
            messages = messages.filter(id__gt=self.notified_up_to_id)
        return messages


class ConversationMessageQuerySet(QuerySet):
    def exclude_replies(self):
        return self.filter(Q(thread_id=None) | Q(id=F('thread_id')))

    def only_threads_with_user(self, user):
        return self.filter(participants__user=user)

    def only_threads_and_replies(self):
        return self.exclude(thread_id=None)

    def only_replies(self):
        return self.filter(~Q(thread_id=None) & ~Q(id=F('thread_id')))

    def annotate_replies_count(self):
        return self.annotate(
            replies_count=Count('thread_messages', filter=~Q(thread_messages__id=F('thread_id')), distinct=True)
        )

    def annotate_unread_replies_count_for(self, user):
        unread_replies_filter = Q(
            participants__user=user,
        ) & ~Q(thread_messages__id=F('thread_id')  # replies have id != thread_id
               ) & (Q(participants__seen_up_to=None) | Q(thread_messages__id__gt=F('participants__seen_up_to')))
        return self.annotate(
            unread_replies_count=Count('thread_messages', filter=unread_replies_filter, distinct=True)
        )


class ConversationMessageManager(BaseManager.from_queryset(ConversationMessageQuerySet)):
    def create(self, **kwargs):
        if 'thread' not in kwargs:
            # make sure author is participant (to receive notifications)
            conversation = kwargs.get('conversation')
            author = kwargs.get('author')
            conversation.conversationparticipant_set.get_or_create(user=author)

        obj = super().create(**kwargs)
        # clear cached value
        if obj.thread and hasattr(obj.thread, '_replies_count'):
            del obj.thread._replies_count
        return obj


class ConversationMessage(BaseModel, UpdatedAtMixin):
    """A message in the conversation by a particular user."""

    objects = ConversationMessageManager()

    author = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = ForeignKey(Conversation, related_name='messages', on_delete=models.CASCADE)
    thread = ForeignKey('self', related_name='thread_messages', null=True, on_delete=models.CASCADE)

    content = TextField()
    received_via = CharField(max_length=40, blank=True)
    edited_at = DateTimeField(null=True)

    latest_message = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        related_name='thread_latest_message',
    )

    def save(self, **kwargs):
        creating = self.pk is None
        old = type(self).objects.get(pk=self.pk) if self.pk else None
        if old is not None and old.content != self.content:
            self.edited_at = timezone.now()

        super().save(**kwargs)

        if creating:
            # keep latest_message reference up-to-date
            if self.is_thread_reply():
                # update thread
                thread = self.thread
                thread.latest_message = self
                thread.save()
            else:
                # update conversation
                conversation = self.conversation
                conversation.latest_message = self
                conversation.save()

    def content_rendered(self, **kwargs):
        return markdown.render(self.content, **kwargs)

    def is_recent(self):
        return self.created_at >= timezone.now() - relativedelta(days=settings.MESSAGE_EDIT_DAYS)

    def is_first_in_thread(self):
        return self.id == self.thread_id

    def is_thread_reply(self):
        return self.thread_id is not None and self.id != self.thread_id

    @property
    def replies_count(self):
        if hasattr(self, '_replies_count'):
            return self._replies_count
        else:
            return self.thread_messages.only_replies().count()

    @replies_count.setter
    def replies_count(self, value):
        self._replies_count = value


class ConversationThreadParticipant(BaseModel, UpdatedAtMixin):
    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    thread = ForeignKey(ConversationMessage, related_name='participants', on_delete=models.CASCADE)
    seen_up_to = ForeignKey(
        ConversationMessage,
        null=True,
        on_delete=models.SET_NULL,
        related_name='threadparticipants_seen_up_to',
    )
    notified_up_to = ForeignKey(
        ConversationMessage,
        null=True,
        on_delete=models.SET_NULL,
        related_name='threadparticipants_notified_up_to',
    )
    muted = BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'thread']

    def unseen_and_unnotified_messages(self):
        messages = self.thread.thread_messages.only_replies()
        if self.seen_up_to_id is not None:
            messages = messages.filter(id__gt=self.seen_up_to_id)
        if self.notified_up_to_id is not None:
            messages = messages.filter(id__gt=self.notified_up_to_id)
        return messages


class ConversationMixin(object):
    # TODO: including this should automatically wireup a signal to create/destroy with target

    @property
    def conversation(self):
        return Conversation.objects.get_or_create_for_target(self)

    @property
    def has_ended(self):
        """Override this property if the conversation should be closed after the target has ended"""
        return False

    @property
    def conversation_is_group_public(self):
        """Override this property if the conversation should not be accessible to all group members"""
        return True

    @property
    def group(self):
        """Returns the group that the target belongs to
        Override this property if you have the group at another location
        """
        return self.group


class ConversationMessageReaction(BaseModel):
    """Emoji reactions to messages."""
    # User who gave the reaction
    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = ForeignKey(ConversationMessage, related_name='reactions', on_delete=models.CASCADE)
    # Name of the emoji
    name = CharField(max_length=100)

    class Meta:
        unique_together = ['user', 'name', 'message']
