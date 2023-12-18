import random
from datetime import timedelta
from unittest.mock import patch

from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.activities.factories import ActivityFactory, ActivityTypeFactory
from karrot.activities.models import to_range, Activity, Feedback, FeedbackNoShow
from karrot.groups.factories import GroupFactory
from karrot.groups.roles import GROUP_MEMBER
from karrot.history.models import History
from karrot.places.factories import PlaceFactory
from karrot.places.models import PlaceStatus
from karrot.users.factories import VerifiedUserFactory
from karrot.utils.tests.fake import faker


def generate_stats(n):
    return [
        {
            "ms": random.randint(1, 3000),
            "ms_resources": random.randint(1, 3000),
            "first_load": random.choice([True, False]),
            "logged_in": random.choice([True, False]),
            "mobile": random.choice([True, False]),
            "app": random.choice([True, False]),
            "browser": faker.name(),
            "os": faker.name(),
            "dev": random.choice([True, False]),
            "group": random.choice([random.randint(1, 100), None]),
            "route_name": faker.name(),
            "route_path": faker.name(),
        }
        for n in range(n)
    ]


@patch("karrot.stats.stats.write_points")
class TestStatsInfoAPI(APITestCase):
    def test_writing_a_point(self, write_points):
        self.maxDiff = None
        stat = {
            "ms": 1000,
            "ms_resources": 5000,
            "first_load": True,
            "logged_in": True,
            "mobile": False,
            "app": False,
            "browser": "firefox",
            "os": "linux",
            "dev": False,
            "group": 1,
            "route_name": "group",
            "route_path": "/group",
            "route_params": {
                "group_id": 5,
                "foo": "bar",
            },
        }
        response = self.client.post("/api/stats/", data={"stats": [stat]}, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points,), kwargs = write_points.call_args
        self.assertEqual(
            points,
            [
                {
                    "measurement": "karrot.stats.frontend",
                    "fields": {
                        "ms": stat["ms"],
                        "ms_resources": stat["ms_resources"],
                        "route_path": "/group",
                    },
                    "tags": {
                        "first_load": True,
                        "logged_in": True,
                        "mobile": False,
                        "app": False,
                        "browser": "firefox",
                        "os": "linux",
                        "dev": False,
                        "group": 1,
                        "route_name": "group",
                    },
                }
            ],
        )

    def test_writing_many_points(self, write_points):
        n = 50
        stats = generate_stats(n)
        response = self.client.post("/api/stats/", data={"stats": stats}, format="json")
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)
        self.assertEqual(len(write_points.call_args_list), 1)
        (points,), kwargs = write_points.call_args
        self.assertEqual(len(points), n)

    def test_writing_too_many_points(self, write_points):
        n = 60
        stats = generate_stats(n)
        response = self.client.post("/api/stats/", data={"stats": stats}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)


class TestActivityHistoryStatsAPI(APITestCase):
    def setUp(self):
        self.user = VerifiedUserFactory()
        self.user2 = VerifiedUserFactory()
        self.group = GroupFactory(members=[self.user, self.user2])
        self.place = PlaceFactory(group=self.group)

    def test_with_no_activity(self):
        self.client.force_login(user=self.user)
        response = self.client.get("/api/stats/activity-history/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0, response.data)

    def setup_activity(self, max_participants=1):
        self.date = to_range(timezone.now() + timedelta(days=33))
        self.just_before_the_activity_starts = self.date.start - timedelta(hours=1)
        self.after_the_activity_is_over = self.date.end + timedelta(hours=2)
        self.activity = ActivityFactory(
            place=self.place,
            date=self.date,
            participant_types=[{"role": GROUP_MEMBER, "max_participants": max_participants}],
        )

    def test_activity_done(self):
        self.setup_activity()
        self.client.force_login(user=self.user)
        self.client.post(f"/api/activities/{self.activity.id}/add/")
        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                        }
                    )
                ],
                response.data,
            )

    def test_activity_done_by_multiple_users(self):
        self.setup_activity(max_participants=2)
        self.client.force_login(user=self.user2)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        self.client.force_login(user=self.user)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            for user in [self.user, self.user2]:
                response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": user.id})
                self.assertEqual(len(response.data), 1)
                self.assertEqual(
                    [dict(entry) for entry in response.data],
                    [
                        self.expected_entry(
                            {
                                "done_count": 1,
                            }
                        )
                    ],
                    response.data,
                )

    def test_activity_missed(self):
        self.setup_activity()
        self.client.force_login(user=self.user)
        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            # only relevant when no user specified
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "missed_count": 1,
                        }
                    )
                ],
                response.data,
            )

    def test_join_and_leave_activity_missed(self):
        self.setup_activity()
        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        with freeze_time(self.just_before_the_activity_starts, tick=True):
            # leave again, so soon! just before it's due to begin! naughty!
            self.client.post(f"/api/activities/{self.activity.id}/remove/")

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "leave_count": 1,
                            "leave_late_count": 1,
                            "leave_missed_count": 1,
                            "leave_missed_late_count": 1,
                        }
                    )
                ],
                response.data,
            )

    def test_reports_left_late_if_activity_not_full(self):
        self.setup_activity(max_participants=2)

        # user2 will participate
        self.client.force_login(user=self.user2)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        with freeze_time(self.just_before_the_activity_starts, tick=True):
            # leave again, so soon! just before it's due to begin! naughty!
            self.client.post(f"/api/activities/{self.activity.id}/remove/")

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            # only 1 user participated for a 2 person activity, so this is naughty!
            self.assertEqual(len(response.data), 1, response.data)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "leave_count": 1,
                            "leave_late_count": 1,
                        }
                    )
                ],
                response.data,
            )

    def test_leave_missed(self):
        self.setup_activity()
        self.client.force_login(user=self.user)

        # join activity (well before it starts)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        with freeze_time(self.just_before_the_activity_starts, tick=True):
            # leave again, so soon! just before it's due to begin! naughty!
            self.client.post(f"/api/activities/{self.activity.id}/remove/")

            # but phew! this time user 2 will do it instead...
            self.client.force_login(user=self.user2)
            self.client.post(f"/api/activities/{self.activity.id}/add/")

        self.client.force_login(user=self.user)

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1, response.data)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "leave_count": 1,
                            "leave_late_count": 1,
                            # the activity was not missed, so not too bad...
                            "leave_missed_count": 0,
                            "leave_missed_late_count": 0,
                        }
                    )
                ],
                response.data,
            )

    def test_join_leave_repeatedly_only_counts_once_per_user(self):
        self.setup_activity(max_participants=2)

        for user in [self.user, self.user2]:
            self.client.force_login(user=user)
            # repeatedly join and leave
            for _ in range(5):
                self.client.post(f"/api/activities/{self.activity.id}/add/")
                self.client.post(f"/api/activities/{self.activity.id}/remove/")

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            self.client.force_login(user=self.user)
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "missed_count": 1,
                            "leave_count": 2,
                            "leave_late_count": 0,
                            "leave_missed_count": 2,
                            "leave_missed_late_count": 0,
                        }
                    )
                ],
                response.data,
            )

    def test_feedback(self):
        self.setup_activity()
        self.client.force_login(user=self.user)
        # join activity (well before it starts)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        # other user joins too
        self.client.force_login(user=self.user2)
        self.client.post(f"/api/activities/{self.activity.id}/add/")
        self.client.force_login(user=self.user)

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            # both users give some feedback!
            Feedback.objects.create(given_by=self.user, about=self.activity, weight=1.5, comment="foo")
            Feedback.objects.create(given_by=self.user2, about=self.activity, weight=2.1, comment="foo")

            # request just for one user
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(len(response.data), 1, response.data)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                            "feedback_count": 1,
                            "feedback_weight": 1.5,
                        }
                    )
                ],
                response.data,
            )

            # or all users
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(len(response.data), 1, response.data)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                            "feedback_count": 2,
                            "feedback_weight": 3.6,
                        }
                    )
                ],
                response.data,
            )

    def test_activity_type_filter(self):
        self.setup_activity()
        other_activity_type = ActivityTypeFactory(group=self.group)
        self.client.force_login(user=self.user)
        self.client.post(f"/api/activities/{self.activity.id}/add/")
        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()

            # filter by matching activity type id
            response = self.client.get(
                "/api/stats/activity-history/",
                {"group": self.group.id, "activity_type": self.activity.activity_type.id},
            )
            self.assertEqual(len(response.data), 1, response.data)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                        }
                    )
                ],
                response.data,
            )

            # or a different one...
            response = self.client.get(
                "/api/stats/activity-history/", {"group": self.group.id, "activity_type": other_activity_type.id}
            )
            self.assertEqual(len(response.data), 0, response.data)

    def test_with_archived_place(self):
        self.setup_activity()
        self.client.force_login(user=self.user)
        self.client.post(f"/api/activities/{self.activity.id}/add/")
        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()

            self.place.status = PlaceStatus.ARCHIVED.value
            self.place.save()

            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id, "user": self.user.id})
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                        }
                    )
                ],
                response.data,
            )

    def test_reports_no_shows(self):
        self.setup_activity(max_participants=2)
        self.client.force_login(user=self.user)
        # join activity (well before it starts)
        self.client.post(f"/api/activities/{self.activity.id}/add/")

        # other user joins too
        self.client.force_login(user=self.user2)
        response = self.client.post(f"/api/activities/{self.activity.id}/add/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.client.force_login(user=self.user)

        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            # user reports that user2 didn't show up
            response = self.client.post(
                "/api/feedback/",
                {
                    "about": self.activity.id,
                    "comment": "THEY BAILED ON ME!!!!!",
                    "weight": 1,
                    "no_shows": [{"user": self.user2.id}],
                },
                format="json",
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(len(response.data), 1)
            self.assertEqual(
                [dict(entry) for entry in response.data],
                [
                    self.expected_entry(
                        {
                            "done_count": 1,
                            "no_show_count": 1,
                            "feedback_count": 1,
                            "feedback_weight": 1.0,
                        }
                    )
                ],
                response.data,
            )

    def test_ignores_history_with_null_activity(self):
        """There are some old db entries that might have null activity

        They should not be included in any of the counts, there are not
        many, and they weren't ever included in the stats, so we maintain that...
        """
        self.setup_activity()
        with freeze_time(self.after_the_activity_is_over, tick=True):
            Activity.objects.process_finished_activities()
            self.client.force_login(user=self.user)

            # normally should have 1 entry
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(len(response.data), 1, response.data)

            # remove it and check it doesn't give a result
            History.objects.filter(activity=self.activity).update(activity=None)
            response = self.client.get("/api/stats/activity-history/", {"group": self.group.id})
            self.assertEqual(len(response.data), 0, response.data)

    def test_no_show_two_feedbacks_about_same_person(self):
        users = [VerifiedUserFactory() for _ in range(4)]
        group = GroupFactory(members=users)
        place = PlaceFactory(group=group)
        self.assert_scenario(
            {
                "group": group,
                "login_as": users[0],
                "activities": [
                    {
                        "place": place,
                        "participants": [users[0], users[1], users[2]],
                        "no_show_reports": [
                            {"user_from": users[0], "user_to": users[2]},
                            {"user_from": users[1], "user_to": users[2]},
                        ],
                    },
                ],
            },
            [
                self.expected_entry(
                    {
                        "place": place.id,
                        "group": group.id,
                        "done_count": 1,
                        "feedback_count": 2,
                        "no_show_count": 1,
                    }
                )
            ],
        )

    def test_complex_no_shows(self):
        users = [VerifiedUserFactory() for _ in range(5)]
        group = GroupFactory(members=users)
        places = [
            PlaceFactory(
                # they come out in name order, so ensure we match that
                name=f"place_{i}",
                group=group,
            )
            for i in range(3)
        ]
        self.maxDiff = None
        self.assert_scenario(
            {
                "group": group,
                "login_as": users[0],
                "activities": [
                    {
                        "place": places[0],
                        "participants": [users[0], users[1], users[2], users[3]],
                        "no_show_reports": [
                            {"user_from": users[0], "user_to": users[1]},
                            {"user_from": users[1], "user_to": users[3]},
                            {"user_from": users[2], "user_to": users[3]},
                        ],
                    },
                    {
                        "place": places[0],
                        "participants": [users[2], users[3]],
                        "no_show_reports": [
                            {"user_from": users[2], "user_to": users[3]},
                        ],
                    },
                    {
                        "place": places[1],
                        "participants": [users[0], users[1], users[2]],
                        "no_show_reports": [
                            {"user_from": users[0], "user_to": users[2]},
                            {"user_from": users[1], "user_to": users[2]},
                        ],
                    },
                ],
            },
            [
                self.expected_entry(
                    {
                        "place": places[0].id,
                        "group": group.id,
                        "done_count": 2,
                        "feedback_count": 4,
                        "no_show_count": 3,
                    }
                ),
                self.expected_entry(
                    {
                        "place": places[1].id,
                        "group": group.id,
                        "done_count": 1,
                        "feedback_count": 2,
                        "no_show_count": 1,
                    }
                ),
            ],
        )

    def expected_entry(self, data=None):
        return {
            "place": self.place.id,
            "group": self.place.group.id,
            "done_count": 0,
            "missed_count": 0,
            "no_show_count": 0,
            "leave_count": 0,
            "leave_late_count": 0,
            "leave_missed_count": 0,
            "leave_missed_late_count": 0,
            "feedback_count": 0,
            "feedback_weight": 0.0,
            **(data if data else {}),
        }

    def assert_scenario(self, scenario, expects):
        group = scenario["group"]
        login_as = scenario["login_as"]
        for activity_entry in scenario["activities"]:
            activity = ActivityFactory(
                place=activity_entry["place"],
                date=to_range(timezone.now() + timedelta(days=33)),
            )
            for user in activity_entry["participants"]:
                activity.add_participant(user)
            for no_show_report in activity_entry["no_show_reports"]:
                user_from = no_show_report["user_from"]
                user_to = no_show_report["user_to"]
                feedback = Feedback.objects.create(about=activity, given_by=user_from, comment="yay")
                FeedbackNoShow.objects.create(feedback=feedback, user=user_to)

        with freeze_time(timezone.now() + timedelta(days=100), tick=True):
            Activity.objects.process_finished_activities()
            self.client.force_login(user=login_as)
            response = self.client.get("/api/stats/activity-history/", {"group": group.id})
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            self.assertEqual([dict(entry) for entry in response.data], expects, response.data)
