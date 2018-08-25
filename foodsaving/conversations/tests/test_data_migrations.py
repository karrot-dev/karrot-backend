import logging

from django.utils import timezone

from foodsaving.tests.utils import TestMigrations
from foodsaving.utils.tests.fake import faker


class TestConversationGroupMigration(TestMigrations):
    migrate_from = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('groups', '0032_groupmembership_added_by'),
        ('stores', '0029_remove_store_upcoming_notification_hours'),
        ('pickups', '0001_initial'),
        ('applications', '0003_groupapplication_decided_at'),
        ('conversations', '0016_conversation_group'),
    ]
    migrate_to = [
        ('conversations', '0017_set_conversation_group'),
    ]

    def tearDown(self):
        logging.disable(logging.NOTSET)

    def setUpBeforeMigration(self, apps):
        # logging.disable(logging.CRITICAL)
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        Store = apps.get_model('stores', 'Store')
        Conversation = apps.get_model('conversations', 'Conversation')
        PickupDate = apps.get_model('pickups', 'PickupDate')
        GroupApplication = apps.get_model('applications', 'GroupApplication')
        ContentType = apps.get_model('contenttypes', 'ContentType')

        self.group = Group.objects.create(name='hello')
        target_type = ContentType.objects.get(app_label='groups', model='group')
        self.group_conversation = Conversation.objects.create(target_type=target_type, target_id=self.group.id)

        self.none_conversation = Conversation.objects.create()

        self.private_conversation = Conversation.objects.create(is_private=True)

        store = Store.objects.create(group=self.group)
        pickup = PickupDate.objects.create(store=store, date=timezone.now())
        target_type = ContentType.objects.get(app_label='pickups', model='pickupdate')
        self.pickup_conversation = Conversation.objects.create(target_type=target_type, target_id=pickup.id)

        user = User.objects.create(email=faker.email())
        application = GroupApplication.objects.create(user=user, group=self.group)
        target_type = ContentType.objects.get(app_label='applications', model='groupapplication')
        self.application_conversation = Conversation.objects.create(target_type=target_type, target_id=application.id)

    def test_sets_conversation_group(self):
        self.group_conversation.refresh_from_db()
        self.pickup_conversation.refresh_from_db()
        self.application_conversation.refresh_from_db()

        self.assertIsNone(self.none_conversation.target_id)
        self.assertIsNone(self.private_conversation.target_id)
        self.assertEqual(self.group_conversation.group, self.group)
        self.assertEqual(self.pickup_conversation.group, self.group)
        self.assertEqual(self.application_conversation.group, self.group)
