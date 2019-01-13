from dateutil.relativedelta import relativedelta
from factory import DjangoModelFactory, CREATE_STRATEGY, SubFactory, LazyAttribute
from freezegun import freeze_time

from foodsaving.cases.models import Case, OptionTypes
from foodsaving.groups.factories import GroupFactory
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class CaseFactory(DjangoModelFactory):
    class Meta:
        model = Case
        strategy = CREATE_STRATEGY

    group = SubFactory(GroupFactory)
    created_by = SubFactory(UserFactory)
    affected_user = SubFactory(UserFactory)
    topic = LazyAttribute(lambda x: faker.sentence(nb_words=4))


def vote_for(voting, user, type):
    for option in voting.options.all():
        option.votes.create(score=2 if option.type == type else -2, user=user)


def vote_for_further_discussion(**kwargs):
    vote_for(type=OptionTypes.FURTHER_DISCUSSION.value, **kwargs)


def vote_for_no_change(**kwargs):
    vote_for(type=OptionTypes.NO_CHANGE.value, **kwargs)


def fast_forward_to_voting_expiration(voting):
    time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
    return freeze_time(time_when_voting_expires, tick=True)
