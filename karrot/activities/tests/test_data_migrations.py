import datetime
from django.utils import timezone
from psycopg2.extras import DateTimeTZRange

from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


def to_range(date, **kwargs):
    duration = datetime.timedelta(**kwargs) if kwargs else datetime.timedelta(minutes=30)
    return DateTimeTZRange(date, date + duration)


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
        self.assertEqual(
            activity.date_range, DateTimeTZRange(activity.date, activity.date + datetime.timedelta(minutes=30))
        )


class TestConvertWeightIntoSumMigration(TestMigrations):

    migrate_from = [
        ('groups', '0043_auto_20200717_1325'),
        ('places', '0033_auto_20190130_1128'),
        ('users', '0022_auto_20190404_1919'),
        ('activities', '0019_feedback_weight_for_average'),
    ]
    migrate_to = [
        ('activities', '0020_activity_feedback_always_as_sum'),
    ]

    def setUpBeforeMigration(self, apps):
        User = apps.get_model('users', 'User')
        Group = apps.get_model('groups', 'Group')
        GroupMembership = apps.get_model('groups', 'GroupMembership')
        Place = apps.get_model('places', 'Place')
        Activity = apps.get_model('activities', 'Activity')
        ActivityParticipant = apps.get_model('activities', 'ActivityParticipant')
        Feedback = apps.get_model('activities', 'Feedback')
        group = Group.objects.create(name=faker.name())
        place = Place.objects.create(name=faker.name(), group=group)
        user1 = User.objects.create()
        user2 = User.objects.create()
        GroupMembership.objects.create(group=group, user=user1)
        GroupMembership.objects.create(group=group, user=user2)
        activity = Activity.objects.create(place=place, date=to_range(timezone.now()), feedback_as_sum=False)
        ActivityParticipant.objects.create(activity=activity, user=user1)
        ActivityParticipant.objects.create(activity=activity, user=user2)
        feedback1 = Feedback.objects.create(given_by=user1, about=activity, weight=10)
        feedback2 = Feedback.objects.create(given_by=user2, about=activity, weight=20)
        self.activity_id = activity.id
        self.feedback1_id = feedback1.id
        self.feedback2_id = feedback2.id

    def test_foo(self):
        Activity = self.apps.get_model('activities', 'Activity')
        Feedback = self.apps.get_model('activities', 'Feedback')
        activity = Activity.objects.get(pk=self.activity_id)
        feedback1 = Feedback.objects.get(pk=self.feedback1_id)
        feedback2 = Feedback.objects.get(pk=self.feedback2_id)
        self.assertEqual(activity.feedback_set.count(), 2)

        # user1 claimed it was 10kg, user2 claimed 20kg, so in old logic we would call it 15kg (average)
        self.assertEqual(feedback1.weight_for_average, 10)
        self.assertEqual(feedback2.weight_for_average, 20)

        # in new logic that 15kg was split between 2 people, so we would say 7.5kg each
        self.assertEqual(feedback1.weight, 7.5)
        self.assertEqual(feedback2.weight, 7.5)

        # now we've converted it, this should be changed!
        self.assertTrue(activity.feedback_as_sum)
