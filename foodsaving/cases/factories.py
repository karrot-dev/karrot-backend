from dateutil.relativedelta import relativedelta
from factory import DjangoModelFactory, CREATE_STRATEGY, SubFactory, LazyAttribute, post_generation
from freezegun import freeze_time

from foodsaving.cases.models import GroupCase, OptionTypes
from foodsaving.groups import roles
from foodsaving.groups.factories import GroupFactory
from foodsaving.users.factories import UserFactory
from foodsaving.utils.tests.fake import faker


class CaseFactory(DjangoModelFactory):
    class Meta:
        model = GroupCase
        strategy = CREATE_STRATEGY

    group = SubFactory(GroupFactory)
    created_by = SubFactory(UserFactory)
    affected_user = SubFactory(UserFactory)
    topic = LazyAttribute(lambda x: faker.sentence(nb_words=4))

    @post_generation
    def add_members(self, create, extracted, **kwargs):
        self.group.groupmembership_set.get_or_create(user=self.created_by, roles=[roles.GROUP_EDITOR])
        self.group.groupmembership_set.get_or_create(user=self.affected_user)


def vote_for(voting, user, type):
    for option in voting.options.all():
        option.votes.create(score=2 if option.type == type else -2, user=user)


def vote_for_further_discussion(**kwargs):
    vote_for(type=OptionTypes.FURTHER_DISCUSSION.value, **kwargs)


def vote_for_remove_user(**kwargs):
    vote_for(type=OptionTypes.REMOVE_USER.value, **kwargs)


def fast_forward_to_voting_expiration(voting):
    time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
    return freeze_time(time_when_voting_expires, tick=True)


def fast_forward_just_before_voting_expiration(voting):
    time_when_voting_expires = voting.expires_at - relativedelta(hours=1)
    return freeze_time(time_when_voting_expires, tick=True)
