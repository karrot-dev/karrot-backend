from django.test import TestCase

from karrot.applications.factories import ApplicationFactory
from karrot.groups.factories import GroupFactory
from karrot.issues.factories import IssueFactory
from karrot.offers.factories import OfferFactory
from karrot.activities.factories import ActivityFactory
from karrot.places.factories import PlaceFactory
from karrot.status.helpers import unread_conversations
from karrot.users.factories import UserFactory


class TestStatusHelpers(TestCase):
    def test_get_conversation_status_efficiently(self):
        user = UserFactory()
        group = GroupFactory(members=[user])
        place = PlaceFactory(group=group)
        activity = ActivityFactory(place=place)
        application = ApplicationFactory(user=UserFactory(), group=group)
        issue = IssueFactory(group=group)
        offer = OfferFactory(group=group)

        conversations = [t.conversation for t in (group, activity, application, issue, offer)]
        another_user = UserFactory()
        [c.sync_users([user, another_user]) for c in conversations]
        [c.messages.create(content='hey', author=another_user) for c in conversations]

        with self.assertNumQueries(2):
            unread_conversations(user)
