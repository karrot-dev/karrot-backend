from dateutil.relativedelta import relativedelta
from factory import CREATE_STRATEGY, SubFactory, LazyAttribute, post_generation
from factory.django import DjangoModelFactory
from freezegun import freeze_time

from karrot.groups.models import GroupMembership
from karrot.issues.models import Issue, OptionTypes
from karrot.groups import roles
from karrot.groups.factories import GroupFactory
from karrot.users.factories import UserFactory
from karrot.utils.tests.fake import faker


class IssueFactory(DjangoModelFactory):
    class Meta:
        model = Issue
        strategy = CREATE_STRATEGY

    group = SubFactory(GroupFactory)
    created_by = SubFactory(UserFactory)
    affected_user = SubFactory(UserFactory)
    topic = LazyAttribute(lambda x: faker.sentence(nb_words=4))

    @post_generation
    def add_members(self, create, extracted, **kwargs):
        GroupMembership.objects.update_or_create(
            {'roles': [roles.GROUP_EDITOR]},
            user=self.created_by,
            group=self.group,
        )
        self.group.groupmembership_set.get_or_create(user=self.affected_user)
        self.conversation.join(self.created_by)


def vote_for(voting, user, type):
    vote_data = {
        option.id: {
            'score': 2 if option.type == type else -2,
            'option': option,
            'user': user
        }
        for option in voting.options.all()
    }
    voting.save_votes(user=user, vote_data=vote_data)


def vote_for_further_discussion(**kwargs):
    vote_for(type=OptionTypes.FURTHER_DISCUSSION.value, **kwargs)


def vote_for_no_change(**kwargs):
    vote_for(type=OptionTypes.NO_CHANGE.value, **kwargs)


def vote_for_remove_user(**kwargs):
    vote_for(type=OptionTypes.REMOVE_USER.value, **kwargs)


def fast_forward_to_voting_expiration(voting):
    time_when_voting_expires = voting.expires_at + relativedelta(hours=1)
    return freeze_time(time_when_voting_expires, tick=True)


def fast_forward_just_before_voting_expiration(voting):
    time_when_voting_expires = voting.expires_at - relativedelta(hours=1)
    return freeze_time(time_when_voting_expires, tick=True)
