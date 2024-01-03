import datetime

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from karrot.history.models import HistoryTypus
from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


def to_range(date, **kwargs):
    duration = datetime.timedelta(**kwargs) if kwargs else datetime.timedelta(minutes=30)
    return DateTimeTZRange(date, date + duration)


base = [
    ('groups', '0050_enable_agreements_and_participant_types'),
    ('users', '0027_fix_usernames'),
    ('places', '0038_place_default_view'),
    ('activities', '0041_feedbacknoshow'),
]


class TestFixActivityDoneMissedHistory(TestMigrations):

    migrate_from = [
        *base,
        ('history', '0015_history_history_his_typus_c46ce5_idx'),
    ]
    migrate_to = [
        *base,
        ('history', '0016_fix_activity_done_missed_history'),
    ]

    def setUpBeforeMigration(self, apps):
        History = apps.get_model('history', 'History')
        Activity = apps.get_model('activities', 'Activity')
        ActivityType = apps.get_model('activities', 'ActivityType')
        ActivityParticipant = apps.get_model('activities', 'ActivityParticipant')
        ParticipantType = apps.get_model('activities', 'ParticipantType')
        Group = apps.get_model('groups', 'Group')
        User = apps.get_model('users', 'User')
        GroupMembership = apps.get_model('groups', 'GroupMembership')
        Place = apps.get_model('places', 'Place')
        PlaceType = apps.get_model('places', 'PlaceType')

        group = Group.objects.create(name=faker.name())
        user1 = User.objects.create(username=faker.name())
        user2 = User.objects.create(username=faker.name())
        GroupMembership.objects.create(user=user1, group=group)
        GroupMembership.objects.create(user=user2, group=group)

        place_type = PlaceType.objects.create(name=faker.name(), group=group)
        place = Place.objects.create(name=faker.name(), group=group, place_type=place_type)
        activity_type = ActivityType.objects.create(name=faker.name(), group=group)

        # An activity we'll "miss", and someone will join afterwards
        activity1 = Activity.objects.create(
            place=place,
            date=to_range(timezone.now() - datetime.timedelta(hours=3)),
            activity_type=activity_type,
        )
        participant_type1 = ParticipantType.objects.create(activity=activity1)

        # An activity we'll "join", but someone will join afterwards
        activity2 = Activity.objects.create(
            place=place,
            date=to_range(timezone.now() - datetime.timedelta(hours=3)),
            activity_type=activity_type,
        )
        participant_type2 = ParticipantType.objects.create(activity=activity2)
        ActivityParticipant.objects.create(activity=activity2, user=user1, participant_type=participant_type2)

        # Do what would happen in process finished activities
        Activity.objects.update(is_done=True)
        history1 = History.objects.create(
            typus=HistoryTypus.ACTIVITY_MISSED,
            group=activity1.place.group,
            place=activity1.place,
            activity=activity1,
            date=activity1.date.lower,
        )
        history2 = History.objects.create(
            typus=HistoryTypus.ACTIVITY_DONE,
            group=activity1.place.group,
            place=activity1.place,
            activity=activity2,
            date=activity2.date.lower,
        )
        history2.users.set(activity2.participants.all())

        # now someone joins activity1 late
        ActivityParticipant.objects.create(user=user1, activity=activity1, participant_type=participant_type1)

        # and another person join activity2
        ActivityParticipant.objects.create(user=user2, activity=activity2, participant_type=participant_type2)

        self.activity1_id = activity1.id
        self.activity2_id = activity2.id

        self.assertEqual(history1.typus, HistoryTypus.ACTIVITY_MISSED)
        self.assertEqual(history1.users.count(), 0)

        self.assertEqual(history2.typus, HistoryTypus.ACTIVITY_DONE)
        self.assertEqual(history2.users.count(), 1)

    def test_sets_date_range_from_date(self):
        History = self.apps.get_model('history', 'History')
        Activity = self.apps.get_model('activities', 'Activity')
        activity1 = Activity.objects.get(pk=self.activity1_id)
        activity2 = Activity.objects.get(pk=self.activity2_id)
        history1_qs = History.objects.filter(activity=activity1)
        history2_qs = History.objects.filter(activity=activity2)

        # only 1 history still, didn't add a new one
        self.assertEqual(history1_qs.count(), 1)
        history1 = history1_qs.first()

        # now it's DONE, not MISSED
        self.assertEqual(history1.typus, HistoryTypus.ACTIVITY_DONE)
        # and we have a person!
        self.assertEqual(history1.users.count(), 1)

        # only 1 history still, didn't add a new one
        self.assertEqual(history2_qs.count(), 1)
        history2 = history2_qs.first()

        # still DONE
        self.assertEqual(history2.typus, HistoryTypus.ACTIVITY_DONE)
        # but 2 people now \o/
        self.assertEqual(history2.users.count(), 2)
