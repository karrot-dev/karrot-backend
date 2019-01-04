from foodsaving.conversations.models import ConversationParticipant
from foodsaving.groups.factories import GroupFactory
from foodsaving.pickups.factories import PickupDateFactory
from foodsaving.pickups.models import PickupDateCollector
from foodsaving.stores.factories import StoreFactory
from foodsaving.users.factories import UserFactory
from rest_framework.test import APITestCase


class TestPickUpCollectorReceivers(APITestCase):
    def setUp(self):
        self.first_member = UserFactory()
        self.second_member = UserFactory()
        self.group = GroupFactory(members=[self.first_member, self.second_member])
        self.store = StoreFactory(group=self.group)
        self.pickup = PickupDateFactory(store=self.store, collectors=[self.first_member])

    def test_new_collector_marks_existing_messages_as_read(self):
        self.pickup.conversation.messages.create(author=self.first_member, content='foo')
        self.pickup.conversation.messages.create(author=self.first_member, content='bar')

        PickupDateCollector.objects.create(user=self.second_member, pickupdate=self.pickup)

        new_participant = ConversationParticipant.objects.get(
            user=self.second_member, conversation=self.pickup.conversation
        )

        self.assertTrue(new_participant.seen_up_to == self.pickup.conversation.latest_message)
