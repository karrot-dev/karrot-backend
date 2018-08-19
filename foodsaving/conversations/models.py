from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import ForeignKey, TextField, ManyToManyField, BooleanField, CharField, QuerySet, Count, F, Q, \
    Max, Prefetch
from django.db.models.manager import BaseManager
from django.utils import timezone

from foodsaving.base.base_models import BaseModel, UpdatedAtMixin
from foodsaving.utils import markdown


class ConversationQuerySet(models.QuerySet):
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

    def order_by_latest_message_first(self):
        # TODO duplicated with prefetch_for_serializer, maybe can be simplified?
        return self.annotate(last_message_id=Max('messages__id')).order_by(F('last_message_id').desc(nulls_last=True))

    def prefetch_for_serializer(self):
        latest_messages = ConversationMessage.objects.annotate(max_id=Max('conversation__messages__id')
                                                               ).filter(id=F('max_id'))
        return self.prefetch_related(
            Prefetch('messages', queryset=latest_messages, to_attr='latest_messages'),
            'target_type',
            'participants',
            'latest_messages__reactions',  # TODO move into latest_messages queryset
        )

    def annotate_unread_message_count_for(self, user):
        unread_message_filter = Q(conversationparticipant__user=user) & (
            Q(conversationparticipant__seen_up_to=None) | Q(messages__id__gt=F('conversationparticipant__seen_up_to'))
        )
        return self.annotate(unread_message_count=Count('messages', filter=unread_message_filter, distinct=True))


class Conversation(BaseModel, UpdatedAtMixin):
    """A conversation between one or more users."""

    class Meta:
        unique_together = ('target_type', 'target_id')

    objects = ConversationQuerySet.as_manager()

    participants = ManyToManyField(settings.AUTH_USER_MODEL, through='ConversationParticipant')
    is_private = models.BooleanField(default=False)

    target_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, null=True)
    target_id = models.PositiveIntegerField(null=True)
    target = GenericForeignKey('target_type', 'target_id')

    def join(self, user, **kwargs):
        if not self.conversationparticipant_set.filter(user=user).exists():
            ConversationParticipant.objects.create(user=user, conversation=self, **kwargs)

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

    def latest_message(self):
        prefetched = getattr(self, 'latest_messages', None)
        if prefetched is not None:
            if len(prefetched) == 0:
                return None
            return prefetched[0]
        try:
            return self.messages.latest('id')
        except ConversationMessage.DoesNotExist:
            return None

    def type(self):
        if self.is_private:
            return 'private'
        if self.target_type is None:
            return None

        type = str(self.target_type)
        if type == 'pickup date':
            return 'pickup'
        if type == 'group application':
            return 'application'

        return type


class ConversationParticipant(BaseModel, UpdatedAtMixin):
    """The join table between Conversation and User."""
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
    email_notifications = BooleanField(default=True)

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

    def order_by_latest_message_first(self):
        return self.annotate(last_message_id=Max('thread_messages__id')).order_by(
            F('last_message_id').desc(nulls_last=True)
        )


class ConversationMessageManager(BaseManager.from_queryset(ConversationMessageQuerySet)):
    def create(self, **kwargs):
        obj = super().create(**kwargs)
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


class ConversationMessageReaction(BaseModel):
    """Emoji reactions to messages."""
    # User who gave the reaction
    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    message = ForeignKey(ConversationMessage, related_name='reactions', on_delete=models.CASCADE)
    # Name of the emoji
    name = CharField(max_length=100)

    class Meta:
        unique_together = ['user', 'name', 'message']
