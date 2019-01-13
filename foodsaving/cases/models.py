from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from enum import Enum

from foodsaving.base.base_models import BaseModel
from foodsaving.conversations.models import ConversationMixin
from foodsaving.groups.models import GroupMembership


class CaseTypes(Enum):
    CONFLICT_RESOLUTION = 'conflict_resolution'


class Case(BaseModel, ConversationMixin):
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE, related_name='cases')
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cases_opened')
    is_decided = models.BooleanField(default=False)
    type = models.TextField(
        default=CaseTypes.CONFLICT_RESOLUTION.value,
        choices=[(status.value, status.value) for status in CaseTypes],
    )
    topic = models.TextField()
    affected_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE, related_name='affected_by_case'
    )

    def decide(self):
        self.is_decided = True
        self.save()

    def save(self, **kwargs):
        super().save(**kwargs)

        if self.votings.count() == 0:
            voting = self.votings.create()
            voting.create_options(self.affected_user)


def voting_expiration_time():
    return timezone.now() + relativedelta(days=settings.CASE_VOTING_DURATION_DAYS)


class Voting(BaseModel):
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
        GroupMembership.objects.filter(
            group=self.voting.case.group,
            user=self.affected_user,
        ).delete()


class Vote(BaseModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='votes_given')
    option = models.ForeignKey(Option, on_delete=models.CASCADE, related_name='votes')
    score = models.IntegerField()
