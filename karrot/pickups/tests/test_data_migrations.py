import datetime
from django.utils import timezone
from psycopg2.extras import DateTimeTZRange

from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestConvertPickupDateToRangeMigration(TestMigrations):
    migrate_from = [
        ("groups", "0035_groupmembership_removal_notification_at"),
        ("places", "0031_auto_20181216_2133"),
        ("pickups", "0010_pickupdate_date_range"),
    ]
    migrate_to = [
        ("pickups", "0011_pickupdate_migrate_to_date_range"),
    ]

    def setUpBeforeMigration(self, apps):
        Group = apps.get_model("groups", "Group")
        Place = apps.get_model("places", "Place")
        PickupDate = apps.get_model("pickups", "PickupDate")
        group = Group.objects.create(name=faker.name())
        place = Place.objects.create(name=faker.name(), group=group)
        pickup = PickupDate.objects.create(place=place, date=timezone.now())
        self.assertIsNone(pickup.date_range)
        self.pickup_id = pickup.id

    def test_sets_date_range_from_date(self):
        PickupDate = self.apps.get_model("pickups", "PickupDate")
        pickup = PickupDate.objects.get(pk=self.pickup_id)
        self.assertIsNotNone(pickup.date_range)
        self.assertEqual(
            pickup.date_range,
            DateTimeTZRange(pickup.date, pickup.date + datetime.timedelta(minutes=30)),
        )
