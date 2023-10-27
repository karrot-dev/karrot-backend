from django.utils import timezone

from karrot.history.models import HistoryTypus
from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


class TestPlaceArchivedAtMigration(TestMigrations):
    migrate_from = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
        ('places', '0039_place_archived_at_placetype_archived_at'),
    ]
    migrate_to = [
        ('places', '0040_set_place_archived_at'),
    ]

    def setUpBeforeMigration(self):
        self.apps.get_model('users', 'User')
        Group = self.apps.get_model('groups', 'Group')
        PlaceType = self.apps.get_model('places', 'PlaceType')
        Place = self.apps.get_model('places', 'Place')
        History = self.apps.get_model('history', 'History')

        group = Group.objects.create(name=faker.name())
        place_type = PlaceType.objects.create(name=faker.name(), group=group)
        place1 = Place.objects.create(name=faker.name(), group=group, place_type=place_type)
        place2 = Place.objects.create(name=faker.name(), group=group, place_type=place_type)

        for place in [place1, place2]:
            place.status = 'archived'
            place.save()

        self.place1_id = place1.id
        self.place2_id = place2.id

        history_data = dict(
            typus=HistoryTypus.STORE_MODIFY,
            group=group,
            payload={'status': 'archived'},
            # simplified version...
            before={'id': place1.id},
            after={'id': place1.id},
        )

        # have to add the history entry manually, so it's not amazing test, but yeah...
        # only created it for place1 so we can check place2 uses now()
        history = History.objects.create(
            date=faker.date_time_between('-30d', 'now', timezone.utc),
            **history_data,
        )
        # create an older one, that should not be used
        History.objects.create(
            date=faker.date_time_between('-60d', '-40d', timezone.utc),
            **history_data,
        )
        self.history_id = history.id

    def test_updates_archived_at_from_history(self):
        History = self.apps.get_model('history', 'History')
        Place = self.apps.get_model('places', 'Place')
        history = History.objects.get(id=self.history_id)

        place1 = Place.objects.get(id=self.place1_id)
        place2 = Place.objects.get(id=self.place2_id)
        diff_seconds1 = abs(timezone.now() - place1.archived_at).total_seconds()
        diff_seconds2 = abs(timezone.now() - place2.archived_at).total_seconds()

        self.assertEqual(place1.archived_at, history.date)
        self.assertNotEqual(place2.archived_at, history.date)

        self.assertGreater(diff_seconds1, 5)
        self.assertLess(diff_seconds2, 5)


class TestPlaceTypeArchivedAtMigration(TestMigrations):
    migrate_from = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
        ('places', '0039_place_archived_at_placetype_archived_at'),
    ]
    migrate_to = [
        ('places', '0040_set_place_archived_at'),
    ]

    def setUpBeforeMigration(self):
        self.apps.get_model('users', 'User')
        Group = self.apps.get_model('groups', 'Group')
        PlaceType = self.apps.get_model('places', 'PlaceType')
        History = self.apps.get_model('history', 'History')

        group = Group.objects.create(name=faker.name())
        place_type1 = PlaceType.objects.create(name=faker.name(), group=group)
        place_type2 = PlaceType.objects.create(name=faker.name(), group=group)

        for place_type in [place_type1, place_type2]:
            place_type.status = 'archived'
            place_type.save()

        self.place_type1_id = place_type1.id
        self.place_type2_id = place_type2.id

        history_data = dict(
            typus=HistoryTypus.PLACE_TYPE_MODIFY,
            group=group,
            payload={'status': 'archived'},
            # simplified version...
            before={'id': place_type1.id},
            after={'id': place_type1.id},
        )

        # have to add the history entry manually, so it's not amazing test, but yeah...
        # only created it for place1 so we can check place2 uses now()
        history = History.objects.create(
            date=faker.date_time_between('-30d', 'now', timezone.utc),
            **history_data,
        )
        # create an older one, that should not be used
        History.objects.create(
            date=faker.date_time_between('-60d', '-40d', timezone.utc),
            **history_data,
        )
        self.history_id = history.id

    def test_updates_archived_at_from_history(self):
        History = self.apps.get_model('history', 'History')
        PlaceType = self.apps.get_model('places', 'PlaceType')
        history = History.objects.get(id=self.history_id)

        place_type1 = PlaceType.objects.get(id=self.place_type1_id)
        place_type2 = PlaceType.objects.get(id=self.place_type2_id)
        diff_seconds1 = abs(timezone.now() - place_type1.archived_at).total_seconds()
        diff_seconds2 = abs(timezone.now() - place_type2.archived_at).total_seconds()

        self.assertEqual(place_type1.archived_at, history.date)
        self.assertNotEqual(place_type2.archived_at, history.date)

        self.assertGreater(diff_seconds1, 5)
        self.assertLess(diff_seconds2, 5)


class TestPlaceStatusMigration(TestMigrations):
    migrate_from = [
        ('groups', '0050_enable_agreements_and_participant_types'),
        ('places', '0043_placetype_description_placestatus_place_status_next'),
    ]
    migrate_to = [
        ('places', '0044_migrate_place_statuses'),
    ]

    def setUpBeforeMigration(self):
        self.apps.get_model('users', 'User')
        Group = self.apps.get_model('groups', 'Group')
        Place = self.apps.get_model('places', 'Place')
        PlaceType = self.apps.get_model('places', 'PlaceType')

        group1 = Group.objects.create(name=faker.name())
        group2 = Group.objects.create(name=faker.name())

        for group in [group1, group2]:
            place_type = PlaceType.objects.create(name=faker.name(), group=group)
            for _ in range(3):
                for status in ('created', 'negotiating', 'active', 'declined'):
                    Place.objects.create(
                        name=faker.name(),
                        group=group,
                        place_type=place_type,
                        status=status,
                    )

        self.group1_id = group1.id
        self.group2_id = group2.id

    def test_converts_to_status_next(self):
        Group = self.apps.get_model('groups', 'Group')
        Place = self.apps.get_model('places', 'Place')
        PlaceStatus = self.apps.get_model('places', 'PlaceStatus')

        group1 = Group.objects.get(id=self.group1_id)
        group2 = Group.objects.get(id=self.group2_id)

        for group in [group1, group2]:
            self.assertEqual(PlaceStatus.objects.filter(group=group).count(), 4)
            for status in ('created', 'negotiating', 'active', 'declined'):
                status = PlaceStatus.objects.get(group=group, name=status.capitalize())
                self.assertEqual(Place.objects.filter(group=group, status_next=status).count(), 3)
