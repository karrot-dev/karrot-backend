from rest_framework.test import APITestCase

from karrot.activities.factories import ActivityFactory
from karrot.activities.models import ActivityParticipant
from karrot.conversations.models import ConversationParticipant
from karrot.groups.factories import GroupFactory
from karrot.places.factories import PlaceFactory
from karrot.users.factories import UserFactory


class TestPickUpParticipantReceivers(APITestCase):
    def setUp(self):
        self.first_member = UserFactory()
        self.second_member = UserFactory()
        self.third_member = UserFactory()
        self.group = GroupFactory(members=[self.first_member, self.second_member, self.third_member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, participants=[self.first_member])

    def test_new_participant_marks_existing_messages_as_read(self):
        self.activity.conversation.messages.create(author=self.first_member, content="foo")
        self.activity.conversation.messages.create(author=self.first_member, content="bar")

        self.activity.add_participant(self.second_member)

        new_participant = ConversationParticipant.objects.get(
            user=self.second_member, conversation=self.activity.conversation
        )

        self.assertTrue(new_participant.seen_up_to == self.activity.conversation.latest_message)

    def test_new_participant_does_not_remove_conversation_subscribers(self):
        self.activity.conversation.join(self.second_member)
        self.assertIn(self.second_member, self.activity.conversation.participants.all())
        self.activity.add_participant(self.third_member)
        self.assertIn(self.second_member, self.activity.conversation.participants.all())

    def test_participant_leaving_does_not_remove_conversation_subscribers(self):
        self.activity.conversation.join(self.second_member)
        self.assertIn(self.second_member, self.activity.conversation.participants.all())
        ActivityParticipant.objects.filter(user=self.first_member, activity=self.activity).delete()
        self.assertIn(self.second_member, self.activity.conversation.participants.all())

    def test_schedules_activity_reminder(self):
        participant = self.activity.add_participant(self.second_member)
        self.assertIsNotNone(participant.reminder_task_id)
