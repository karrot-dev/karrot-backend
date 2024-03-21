import datetime
from random import randint

from django.db.backends.postgresql.psycopg_any import DateTimeTZRange
from django.utils import timezone

from karrot.history.models import HistoryTypus
from karrot.tests.utils import TestMigrations
from karrot.utils.tests.fake import faker


def to_range(date, **kwargs):
    duration = datetime.timedelta(**kwargs) if kwargs else datetime.timedelta(minutes=30)
    return DateTimeTZRange(date, date + duration)


class TestConvertActivityToRangeMigration(TestMigrations):
    migrate_from = [
        ("groups", "0035_groupmembership_removal_notification_at"),
        ("places", "0031_auto_20181216_2133"),
        ("activities", "0010_activity_date_range"),
    ]
    migrate_to = [
        ("activities", "0011_activity_migrate_to_date_range"),
    ]

    def setUpBeforeMigration(self):
        Group = self.apps.get_model("groups", "Group")
        Place = self.apps.get_model("places", "Place")
        Activity = self.apps.get_model("activities", "Activity")
        group = Group.objects.create(name=faker.name())
        place = Place.objects.create(name=faker.name(), group=group)
        activity = Activity.objects.create(place=place, date=timezone.now())
        self.assertIsNone(activity.date_range)
        self.activity_id = activity.id

    def test_sets_date_range_from_date(self):
        Activity = self.apps.get_model("activities", "Activity")
        activity = Activity.objects.get(pk=self.activity_id)
        self.assertIsNotNone(activity.date_range)
        self.assertEqual(
            activity.date_range, DateTimeTZRange(activity.date, activity.date + datetime.timedelta(minutes=30))
        )


class TestConvertWeightIntoSumMigration(TestMigrations):
    migrate_from = [
        ("groups", "0043_auto_20200717_1325"),
        ("places", "0033_auto_20190130_1128"),
        ("users", "0022_auto_20190404_1919"),
        ("activities", "0019_feedback_weight_for_average"),
    ]
    migrate_to = [
        ("activities", "0020_activity_feedback_always_as_sum"),
    ]

    def setUpBeforeMigration(self):
        User = self.apps.get_model("users", "User")
        Group = self.apps.get_model("groups", "Group")
        GroupMembership = self.apps.get_model("groups", "GroupMembership")
        Place = self.apps.get_model("places", "Place")
        Activity = self.apps.get_model("activities", "Activity")
        ActivityParticipant = self.apps.get_model("activities", "ActivityParticipant")
        Feedback = self.apps.get_model("activities", "Feedback")
        group = Group.objects.create(name=faker.name())
        place = Place.objects.create(name=faker.name(), group=group)
        activity1 = Activity.objects.create(place=place, date=to_range(timezone.now()), feedback_as_sum=False)
        activity2 = Activity.objects.create(place=place, date=to_range(timezone.now()), feedback_as_sum=False)
        user1 = User.objects.create()
        user2 = User.objects.create()
        user3 = User.objects.create()
        for user in [user1, user2, user3]:
            GroupMembership.objects.create(group=group, user=user)
            ActivityParticipant.objects.create(activity=activity1, user=user)
            ActivityParticipant.objects.create(activity=activity2, user=user)
        feedback1 = Feedback.objects.create(given_by=user1, about=activity1, weight=10)
        feedback2 = Feedback.objects.create(given_by=user2, about=activity1, weight=20)
        feedback3 = Feedback.objects.create(given_by=user3, about=activity1)  # no weight!
        for user in [user1, user2, user3]:
            # and an activity with no weight feedback at all
            Feedback.objects.create(given_by=user, about=activity2)
        self.activity1_id = activity1.id
        self.activity2_id = activity2.id
        self.feedback1_id = feedback1.id
        self.feedback2_id = feedback2.id
        self.feedback3_id = feedback3.id

    def test_migration_of_average_to_sum(self):
        Activity = self.apps.get_model("activities", "Activity")
        Feedback = self.apps.get_model("activities", "Feedback")
        activity1 = Activity.objects.get(pk=self.activity1_id)
        activity2 = Activity.objects.get(pk=self.activity2_id)
        feedback1 = Feedback.objects.get(pk=self.feedback1_id)
        feedback2 = Feedback.objects.get(pk=self.feedback2_id)
        feedback3 = Feedback.objects.get(pk=self.feedback3_id)
        self.assertEqual(activity1.feedback_set.count(), 3)

        # user1 claimed it was 10kg, user2 claimed 20kg, so in old logic we would call it 15kg (average)
        self.assertEqual(feedback1.weight_for_average, 10)
        self.assertEqual(feedback2.weight_for_average, 20)

        # in new logic that 15kg was split between 2 people, so we would say 7.5kg each
        self.assertEqual(feedback1.weight, 7.5)
        self.assertEqual(feedback2.weight, 7.5)
        self.assertEqual(feedback3.weight, None)  # still no weight

        # now we've converted it, this should be changed!
        self.assertTrue(activity1.feedback_as_sum)

        self.assertEqual(activity2.feedback_set.exclude(weight=None).count(), 0)
        self.assertEqual(activity2.feedback_set.filter(weight=None).count(), 3)


class TestSetActivityTypes(TestMigrations):
    migrate_from = [
        ("groups", "0043_auto_20200717_1325"),
        ("places", "0033_auto_20190130_1128"),
        ("activities", "0022_add_activity_types"),
    ]
    migrate_to = [
        ("activities", "0023_create_and_set_activity_types"),
    ]

    def setUpBeforeMigration(self):
        Group = self.apps.get_model("groups", "Group")
        Place = self.apps.get_model("places", "Place")
        Activity = self.apps.get_model("activities", "Activity")
        ActivitySeries = self.apps.get_model("activities", "ActivitySeries")

        for theme in ["foodsaving", "bikekitchen", "general"]:
            group = Group.objects.create(name=faker.name(), theme=theme)
            place = Place.objects.create(name=faker.name(), group=group)
            Activity.objects.create(place=place, date=to_range(timezone.now()))
            ActivitySeries.objects.create(place=place, start_date=timezone.now())

    def test_activity_types_are_created_and_set(self):
        Activity = self.apps.get_model("activities", "Activity")
        ActivitySeries = self.apps.get_model("activities", "ActivitySeries")
        ActivityType = self.apps.get_model("activities", "ActivityType")

        def check_type(theme, type_name):
            activity = Activity.objects.filter(place__group__theme=theme).first()
            self.assertEqual(activity.activity_type.name, type_name)
            series = ActivitySeries.objects.filter(place__group__theme=theme).first()
            self.assertEqual(series.activity_type.name, type_name)

        def check_available_types(theme, expected_type_names):
            type_names = [t.name for t in ActivityType.objects.filter(group__theme=theme)]
            # assertCountEqual is confusingly named, it checks lists, ignoring order
            self.assertCountEqual(type_names, expected_type_names)

        check_available_types("foodsaving", ["Meeting", "Pickup", "Distribution", "Event"])
        check_available_types("bikekitchen", ["Meeting", "Event", "Activity"])
        check_available_types("general", ["Meeting", "Event", "Activity"])

        check_type("foodsaving", "Pickup")
        check_type("bikekitchen", "Activity")
        check_type("general", "Activity")


class TestAddParticipantTypes(TestMigrations):
    migrate_from = [
        ("users", "0027_fix_usernames"),
        ("groups", "0046_groupmembership_must_have_member_role"),
        ("places", "0038_place_default_view"),
        ("activities", "0033_add_participant_types"),
    ]
    migrate_to = [
        ("activities", "0034_backfill_participant_role"),
    ]

    def setUpBeforeMigration(self):
        User = self.apps.get_model("users", "User")
        Group = self.apps.get_model("groups", "Group")
        GroupMembership = self.apps.get_model("groups", "GroupMembership")
        PlaceType = self.apps.get_model("places", "PlaceType")
        Place = self.apps.get_model("places", "Place")
        ActivityType = self.apps.get_model("activities", "ActivityType")
        Activity = self.apps.get_model("activities", "Activity")
        ActivitySeries = self.apps.get_model("activities", "ActivitySeries")
        ActivityParticipant = self.apps.get_model("activities", "ActivityParticipant")

        group = Group.objects.create(name=faker.name())
        place_type = PlaceType.objects.create(name=faker.name(), group=group)
        place = Place.objects.create(name=faker.name(), group=group, place_type=place_type)
        activity_type = ActivityType.objects.create(name=faker.name(), group=group)
        user = User.objects.create(username=faker.user_name())
        GroupMembership.objects.create(group=group, user=user)

        for _ in range(5):
            ActivitySeries.objects.create(
                place=place,
                start_date=timezone.now(),
                activity_type=activity_type,
            )

        for _ in range(20):
            activity = Activity.objects.create(
                place=place,
                date=to_range(timezone.now()),
                activity_type=activity_type,
                max_participants=randint(1, 12),
            )
            ActivityParticipant.objects.create(activity=activity, user=user)

    def test_adds_default_participant_types(self):
        Activity = self.apps.get_model("activities", "Activity")
        ActivitySeries = self.apps.get_model("activities", "ActivitySeries")
        ActivityParticipant = self.apps.get_model("activities", "ActivityParticipant")
        ParticipantType = self.apps.get_model("activities", "ParticipantType")
        SeriesParticipantType = self.apps.get_model("activities", "SeriesParticipantType")

        # every activity has at least one participant type
        for activity in Activity.objects.all():
            self.assertGreater(activity.participant_types.count(), 0)

        # every series has at least one series participant type
        for series in ActivitySeries.objects.all():
            self.assertGreater(series.participant_types.count(), 0)

        # every participant has a participant type
        self.assertEqual(ActivityParticipant.objects.filter(participant_type=None).count(), 0)

        for pt in ParticipantType.objects.all():
            # all initial ones are for 'member' role
            self.assertEqual(pt.role, "member")
            # and copy the max_participants from the activity
            self.assertEqual(pt.max_participants, pt.activity.max_participants)

        for spt in SeriesParticipantType.objects.all():
            # all initial ones are for 'member' role
            self.assertEqual(spt.role, "member")
            # and copy the max_participants from the series
            self.assertEqual(spt.max_participants, spt.activity_series.max_participants)


class TestActivityTypeArchivedAtMigration(TestMigrations):
    migrate_from = [
        ("groups", "0050_enable_agreements_and_participant_types"),
        ("places", "0038_place_default_view"),
        ("activities", "0044_activitytype_archived_at"),
        ("history", "0015_history_history_his_typus_c46ce5_idx"),
    ]
    migrate_to = [
        ("activities", "0045_set_activity_type_archived_at"),
    ]

    def setUpBeforeMigration(self):
        self.apps.get_model("users", "User")
        Group = self.apps.get_model("groups", "Group")
        PlaceType = self.apps.get_model("places", "PlaceType")
        Place = self.apps.get_model("places", "Place")
        ActivityType = self.apps.get_model("activities", "ActivityType")
        History = self.apps.get_model("history", "History")

        group = Group.objects.create(name=faker.name())
        place_type = PlaceType.objects.create(name=faker.name(), group=group)
        Place.objects.create(name=faker.name(), group=group, place_type=place_type)
        activity_type1 = ActivityType.objects.create(name=faker.name(), group=group)
        activity_type2 = ActivityType.objects.create(name=faker.name(), group=group)

        for activity_type in [activity_type1, activity_type2]:
            activity_type.status = "archived"
            activity_type.save()

        self.activity_type1_id = activity_type1.id
        self.activity_type2_id = activity_type2.id

        history_data = {
            "typus": HistoryTypus.ACTIVITY_TYPE_MODIFY,
            "group": activity_type.group,
            "payload": {"status": "archived"},
            # simplified version...
            "before": {"id": activity_type1.id},
            "after": {"id": activity_type1.id},
        }

        # have to add the history entry manually, so it's not amazing test, but yeah...
        # only created it for activity_type1 so we can check activity_type2 uses now()
        history = History.objects.create(
            date=faker.date_time_between("-30d", "now", datetime.timezone.utc),
            **history_data,
        )
        # create an older one, that should not be used
        History.objects.create(
            date=faker.date_time_between("-60d", "-40d", datetime.timezone.utc),
            **history_data,
        )
        self.history_id = history.id

    def test_updates_archived_at_from_history(self):
        History = self.apps.get_model("history", "History")
        ActivityType = self.apps.get_model("activities", "ActivityType")
        history = History.objects.get(id=self.history_id)

        activity_type1 = ActivityType.objects.get(id=self.activity_type1_id)
        activity_type2 = ActivityType.objects.get(id=self.activity_type2_id)
        diff_seconds1 = abs(timezone.now() - activity_type1.archived_at).total_seconds()
        diff_seconds2 = abs(timezone.now() - activity_type2.archived_at).total_seconds()

        self.assertEqual(activity_type1.archived_at, history.date)
        self.assertNotEqual(activity_type2.archived_at, history.date)

        self.assertGreater(diff_seconds1, 5)
        self.assertLess(diff_seconds2, 5)
