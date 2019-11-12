from karrot.conversations.models import ConversationParticipant
from karrot.groups.factories import GroupFactory
from karrot.pickups.factories import PickupDateFactory
from karrot.pickups.models import PickupDateCollector
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory
from rest_framework.test import APITestCase


class TestPickUpCollectorReceivers(APITestCase):
    def setUp(self):
        self.first_member = UserFactory()
        self.second_member = UserFactory()
        self.third_member = UserFactory()
        self.group = GroupFactory(members=[self.first_member, self.second_member, self.third_member])
        self.place = PlaceFactory(group=self.group)
        self.pickup = PickupDateFactory(place=self.place, collectors=[self.first_member])

    def test_new_collector_marks_existing_messages_as_read(self):
        self.pickup.conversation.messages.create(author=self.first_member, content='foo')
        self.pickup.conversation.messages.create(author=self.first_member, content='bar')

        PickupDateCollector.objects.create(user=self.second_member, pickupdate=self.pickup)

        new_participant = ConversationParticipant.objects.get(
            user=self.second_member, conversation=self.pickup.conversation
        )

        self.assertTrue(new_participant.seen_up_to == self.pickup.conversation.latest_message)

    def test_new_collector_does_not_remove_conversation_subscribers(self):
        self.pickup.conversation.join(self.second_member)
        self.assertIn(self.second_member, self.pickup.conversation.participants.all())
        PickupDateCollector.objects.create(user=self.third_member, pickupdate=self.pickup)
        self.assertIn(self.second_member, self.pickup.conversation.participants.all())

    def test_collector_leaving_does_not_remove_conversation_subscribers(self):
        self.pickup.conversation.join(self.second_member)
        self.assertIn(self.second_member, self.pickup.conversation.participants.all())
        PickupDateCollector.objects.filter(user=self.first_member, pickupdate=self.pickup).delete()
        self.assertIn(self.second_member, self.pickup.conversation.participants.all())
