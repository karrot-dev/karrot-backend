from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Sum, Q
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


class Case(BaseModel, ConversationMixin):
    objects = CaseQuerySet.as_manager()

    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='cases')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cases_opened')
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
            voting.create_options(self.affected_user)

        if created:
            stats.case_created(self)

    def user_queryset(self):
        editors = Q(groupmembership__in=self.group.groupmembership_set.editors())
        affected_user = Q(id=self.affected_user_id)
        return get_user_model().objects.filter(editors | affected_user)

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


class VotingQuerySet(models.QuerySet):
    def due_soon(self):
        in_some_hours = timezone.now() + relativedelta(hours=settings.VOTING_DUE_SOON_HOURS)
        return self.filter(expires_at__gt=timezone.now(), expires_at__lt=in_some_hours)


def voting_expiration_time():
    return timezone.now() + relativedelta(days=settings.CASE_VOTING_DURATION_DAYS)


class Voting(BaseModel):
    objects = VotingQuerySet.as_manager()

    case = models.ForeignKey(Case, on_delete=models.CASCADE, related_name='votings')
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

    def create_options(self, affected_user):
        options = [
            {
                'type': OptionTypes.FURTHER_DISCUSSION.value,
            },
            {
                'type': OptionTypes.NO_CHANGE.value,
            },
            {
                'type': OptionTypes.REMOVE_USER.value,
                'affected_user': affected_user,
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
    affected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.CASCADE,
        related_name='affected_by_voting_options',
    )
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
                affected_user=option.affected_user,
                message=option.message,
            )

    def _remove_user(self):
        group = self.voting.case.group
        GroupMembership.objects.filter(
            group=group,
            user=self.affected_user,
        ).delete()
        History.objects.create(typus=HistoryTypus.MEMBER_REMOVED, group=group, users=[self.affected_user])


class Vote(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes_given')
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name='votes')
    score = models.IntegerField()
