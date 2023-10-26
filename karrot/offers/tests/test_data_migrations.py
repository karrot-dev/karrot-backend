from django.utils import timezone

from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestOfferArchivedAtMigration(TestMigrations):
    migrate_from = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('users', '0027_fix_usernames'),
        ('offers', '0005_offer_archived_at'),
    ]
    migrate_to = [
        ('offers', '0006_set_archived_at'),
    ]

    def setUpBeforeMigration(self, apps):
        Group = apps.get_model('groups', 'Group')
        GroupMembership = apps.get_model('groups', 'GroupMembership')
        User = apps.get_model('users', 'User')
        Offer = apps.get_model('offers', 'Offer')

        group = Group.objects.create(name=faker.name())
        user = User.objects.create()
        GroupMembership.objects.create(group=group, user=user)
        offer = Offer.objects.create(group=group, user=user, name=faker.name(), description=faker.sentence())
        offer.status = 'archived'
        offer.status_changed_at = timezone.now()
        offer.save()
        self.offer_id = offer.id

    def test_updates_archived_at_from_history(self):
        Offer = self.apps.get_model('offers', 'Offer')
        offer = Offer.objects.get(id=self.offer_id)
        self.assertEqual(offer.archived_at, offer.status_changed_at)
