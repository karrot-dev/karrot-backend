from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from enum import Enum

from foodsaving.base.base_models import BaseModel
from foodsaving.cases import stats
from foodsaving.conversations.models import ConversationMixin
from foodsaving.groups.models import GroupMembership
from foodsaving.history.models import History, HistoryTypus
from foodsaving.utils import markdown


class CaseTypes(Enum):
    CONFLICT_RESOLUTION = 'conflict_resolution'


class CaseStatus(Enum):
    ONGOING = 'ongoing'
    DECIDED = 'decided'
    CANCELLED = 'cancelled'


class CaseQuerySet(models.QuerySet):
    def ongoing(self):
        return self.filter(status=CaseStatus.ONGOING.value)

    def decided(self):
        return self.filter(status=CaseStatus.DECIDED.value)

    def cancelled(self):
        return self.filter(status=CaseStatus.CANCELLED.value)


class GroupCase(BaseModel, ConversationMixin):
    objects = CaseQuerySet.as_manager()

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='cases')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cases_opened')
    participants = models.ManyToManyField(settings.AUTH_USER_MODEL, through='CaseParticipant', related_name='cases')
    status = models.TextField(
        default=CaseStatus.ONGOING.value,
        choices=[(status.value, status.value) for status in CaseStatus],
    )
    type = models.TextField(
        default=CaseTypes.CONFLICT_RESOLUTION.value,
        choices=[(status.value, status.value) for status in CaseTypes],
    )
    topic = models.TextField()
    affected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE, related_name='affected_by_case'
    )

    def decide(self):
        self.status = CaseStatus.DECIDED.value
        self.save()

    def cancel(self):
        self.status = CaseStatus.CANCELLED.value
        self.save()

    def save(self, **kwargs):
        created = self.pk is None
        super().save(**kwargs)

        if self.votings.count() == 0:
            voting = self.votings.create()
            voting.create_options()

        if created:
            stats.case_created(self)

    def latest_voting(self):
        return self.votings.latest('created_at')

    def topic_rendered(self, **kwargs):
        return markdown.render(self.topic, **kwargs)

    def is_decided(self):
        return self.status == CaseStatus.DECIDED.value

    def is_ongoing(self):
        return self.status == CaseStatus.ONGOING.value

    def is_cancelled(self):
        return self.status == CaseStatus.CANCELLED.value


class CaseParticipant(models.Model):
    class Meta:
        unique_together = ('case', 'user')

    case = models.ForeignKey(GroupCase, on_delete=models.CASCADE)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


class VotingQuerySet(models.QuerySet):
    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.VOTING_DUE_SOON_HOURS)
        return self.filter(expires_at__gt=timezone.now(), expires_at__lt=in_some_hours)


def voting_expiration_time():
    return timezone.now() + relativedelta(days=settings.CASE_VOTING_DURATION_DAYS)


class Voting(BaseModel):
    objects = VotingQuerySet.as_manager()

    case = models.ForeignKey(GroupCase, on_delete=models.CASCADE, related_name='votings')
    expires_at = models.DateTimeField(default=voting_expiration_time)
    accepted_option = models.ForeignKey(
        'Option',
        on_delete=models.SET_NULL,
        null=True,
        related_name='accepted_for_voting',
    )

    def is_expired(self):
        return self.expires_at < timezone.now()

    def participant_count(self):
        return get_user_model().objects.filter(votes_given__option__voting=self).distinct().count()

    def create_options(self):
        options = [
            {
                'type': OptionTypes.FURTHER_DISCUSSION.value,
            },
            {
                'type': OptionTypes.NO_CHANGE.value,
            },
            {
                'type': OptionTypes.REMOVE_USER.value,
            },
        ]
        for option in options:
            self.options.create(**option)

    def calculate_results(self):
        options = list(self.options.annotate(_sum_score=Sum('votes__score')).order_by('_sum_score'))
        for option in options:
            option.sum_score = option._sum_score
            option.save()

        accepted_option = options[-1]
        if options[-2].sum_score == accepted_option.sum_score:
            # tie!
            accepted_option = next(o for o in options if o.type == OptionTypes.FURTHER_DISCUSSION.value)

        self.accepted_option = accepted_option
        self.save()

        self.accepted_option.do_action()


class OptionTypes(Enum):
    FURTHER_DISCUSSION = 'further_discussion'
    NO_CHANGE = 'no_change'
    REMOVE_USER = 'remove_user'


class Option(BaseModel):
    voting = models.ForeignKey(Voting, on_delete=models.CASCADE, related_name='options')
    type = models.TextField(choices=[(status.value, status.value) for status in OptionTypes])
    message = models.TextField(null=True)
    sum_score = models.FloatField(null=True)

    def do_action(self):
        if self.type != OptionTypes.FURTHER_DISCUSSION.value:
            self.voting.case.decide()

        if self.type == OptionTypes.FURTHER_DISCUSSION.value:
            self._further_discussion()
        elif self.type == OptionTypes.REMOVE_USER.value:
            self._remove_user()

    def _further_discussion(self):
        new_voting = self.voting.case.votings.create()
        for option in self.voting.options.all():
            new_voting.options.create(
                type=option.type,
                message=option.message,
            )

    def _remove_user(self):
        case = self.voting.case
        group = case.group
        affected_user = case.affected_user
        membership = group.groupmembership_set.get(user=affected_user)
        membership.delete()
        History.objects.create(typus=HistoryTypus.MEMBER_REMOVED, group=group, users=[affected_user])


class Vote(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes_given')
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name='votes')
    score = models.IntegerField()
