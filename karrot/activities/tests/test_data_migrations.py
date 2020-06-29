import datetime
from django.utils import timezone
from psycopg2.extras import DateTimeTZRange

from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestConvertActivityToRangeMigration(TestMigrations):
    migrate_from = [
        ('groups', '0035_groupmembership_removal_notification_at'),
        ('places', '0031_auto_20181216_2133'),
        ('activities', '0010_activity_date_range'),
    ]
    migrate_to = [
        ('activities', '0011_activity_migrate_to_date_range'),
    ]

    def setUpBeforeMigration(self, apps):
        Group = apps.get_model('groups', 'Group')
        Place = apps.get_model('places', 'Place')
        Activity = apps.get_model('activities', 'Activity')
        group = Group.objects.create(name=faker.name())
        place = Place.objects.create(name=faker.name(), group=group)
        activity = Activity.objects.create(place=place, date=timezone.now())
        self.assertIsNone(activity.date_range)
        self.activity_id = activity.id

    def test_sets_date_range_from_date(self):
        Activity = self.apps.get_model('activities', 'Activity')
        activity = Activity.objects.get(pk=self.activity_id)
        self.assertIsNotNone(activity.date_range)
        self.assertEqual(activity.date_range, DateTimeTZRange(activity.date, activity.date + datetime.timedelta(minutes=30)))
