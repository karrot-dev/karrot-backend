from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.db.models import ForeignKey, TextField, ManyToManyField, BooleanField, CharField, QuerySet, Count, F, Q
from django.utils import timezone

from foodsaving.base.base_models import BaseModel, UpdatedAtMixin
from foodsaving.utils import markdown


class ConversationManager(models.Manager):
    @classmethod
    def get_for_target(cls, target):
        return cls.filter_for_target(target).first()

    @classmethod
    def get_or_create_for_target(cls, target):
        return Conversation.objects.get_for_target(target) or Conversation.objects.create(target=target)

    @classmethod
    def filter_for_target(cls, target):
        return Conversation.objects.filter(
            target_id=target.id,
            target_type=ContentType.objects.get_for_model(target),
        )

    @classmethod
    def get_or_create_for_two_users(cls, user1, user2):
        if user1.id == user2.id:
            raise Exception('Users need to be different')
        conv = Conversation.objects.filter(is_private=True, participants=user1)\
            .filter(participants=user2)\
            .first()
        if not conv:
            conv = Conversation.objects.create(is_private=True)
            conv.sync_users([user1, user2])
        return conv


class Conversation(BaseModel, UpdatedAtMixin):
    """A conversation between one or more users."""

    class Meta:
        unique_together = ('target_type', 'target_id')

    objects = ConversationManager()

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


class ConversationParticipant(BaseModel, UpdatedAtMixin):
    """The join table between Conversation and User."""
    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    conversation = ForeignKey(Conversation, on_delete=models.CASCADE)
    seen_up_to = ForeignKey('ConversationMessage', null=True, on_delete=models.SET_NULL)
    email_notifications = BooleanField(default=True)


class ConversationMessageQuerySet(QuerySet):
    def exclude_replies(self):
        return self.filter(Q(thread_id=None) | Q(id=F('thread_id')))

    def only_threads_and_replies(self):
        return self.exclude(thread_id=None)

    def only_replies(self):
        return self.filter(~Q(thread_id=None) & ~Q(id=F('thread_id')))

    def annotate_replies_count(self):
        return self.annotate(replies_count=Count('thread_messages', filter=~Q(id=F('thread_id')), distinct=True))

    def annotate_unread_replies_count_for(self, user):
        unread_replies_filter = Q(
            participants__user=user,
        ) & ~Q(thread_messages__id=F('thread_id')  # replies have id != thread_id
               ) & (Q(participants__seen_up_to=None) | Q(thread_messages__id__gt=F('participants__seen_up_to')))
        return self.annotate(
            unread_replies_count=Count('thread_messages', filter=unread_replies_filter, distinct=True)
        )


class ConversationMessage(BaseModel, UpdatedAtMixin):
    """A message in the conversation by a particular user."""

    objects = ConversationMessageQuerySet.as_manager()

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
        if hasattr(self, '__replies_count'):
            return self.__replies_count
        else:
            return self.thread_messages.only_replies().count()

    @replies_count.setter
    def replies_count(self, value):
        self.__replies_count = value


class ConversationThreadParticipant(BaseModel, UpdatedAtMixin):
    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    thread = ForeignKey(ConversationMessage, related_name='participants', on_delete=models.CASCADE)
    seen_up_to = ForeignKey(ConversationMessage, null=True, on_delete=models.SET_NULL)
    muted = BooleanField(default=False)

    class Meta:
        unique_together = ['user', 'thread']


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
