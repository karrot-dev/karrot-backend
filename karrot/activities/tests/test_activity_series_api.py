from itertools import zip_longest

from dateutil import rrule
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from dateutil.tz import tzlocal
from django.utils import timezone
from django.utils.datetime_safe import datetime
from more_itertools import interleave
from rest_framework import status
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupStatus
from karrot.activities.factories import ActivitySeriesFactory, ActivityTypeFactory
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory


def shift_date_in_local_time(old_date, delta, tz):
    # keeps local time equal, even through daylight saving time transitions
    # e.g. 20:00 + 1 day is always 20:00 on the next day, even if UTC offset changes
    old_date = old_date.astimezone(tz).replace(tzinfo=None)
    new_date = old_date + delta
    return tz.localize(new_date).astimezone(tzlocal())


class TestActivitySeriesCreationAPI(APITestCase, ExtractPaginationMixin):
    """
    This is an integration test for the activity-series API
    """
    def setUp(self):
        self.maxDiff = None
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity_type = ActivityTypeFactory(group=self.group)

    def test_create_and_get_recurring_series(self):
        self.maxDiff = None
        url = '/api/activity-series/'
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[0, 1]  # Monday and Tuesday
        )
        start_date = self.group.timezone.localize(datetime.now().replace(hour=20, minute=0))
        activity_series_data = {
            'activity_type': self.activity_type.id,
            'max_participants': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'start_date': start_date
        }
        start_date = start_date.replace(second=0, microsecond=0)
        self.client.force_login(user=self.member)
        response = self.client.post(url, activity_series_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        series_id = response.data['id']
        self.assertEqual(parse(response.data['start_date']), start_date)
        del response.data['id']
        del response.data['start_date']
        del response.data['dates_preview']
        expected_series_data = {
            'activity_type': self.activity_type.id,
            'max_participants': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'description': '',
            'duration': None,
        }
        self.assertEqual(response.data, expected_series_data)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for _ in response.data:
            self.assertEqual(parse(_['start_date']), start_date)
            del _['id']
            del _['start_date']
            del _['dates_preview']
        self.assertEqual(response.data, [expected_series_data])

        response = self.client.get(url + str(series_id) + '/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(parse(response.data['start_date']), start_date)
        del response.data['id']
        del response.data['start_date']
        del response.data['dates_preview']
        self.assertEqual(response.data, expected_series_data)

        url = '/api/activities/'
        created_activities = []
        # do recurrence calculation in local time to avoid daylight saving time problems
        tz = self.group.timezone
        dates_list = recurrence.replace(
            dtstart=timezone.now().astimezone(tz).replace(hour=20, minute=0, second=0, microsecond=0, tzinfo=None)
        ).between(
            timezone.now().astimezone(tz).replace(tzinfo=None),
            timezone.now().astimezone(tz).replace(tzinfo=None) + relativedelta(weeks=4)
        )
        dates_list = [tz.localize(d) for d in dates_list]

        response = self.get_results(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # verify date field
        for response_data_item, expected_date in zip(response.data, dates_list):
            self.assertEqual(parse(response_data_item['date'][0]), expected_date, response_data_item['date'])

        # verify non-date fields, don't need parsing
        for _ in response.data:
            del _['id']
            del _['date']
            del _['feedback_due']
        for _ in dates_list:
            created_activities.append({
                'activity_type': self.activity_type.id,
                'max_participants': 5,
                'series': series_id,
                'participants': [],
                'place': self.place.id,
                'description': '',
                'feedback_given_by': [],
                'is_disabled': False,
                'has_duration': False,
                'is_done': False,
            })
        self.assertEqual(response.data, created_activities, response.data)

    def test_activity_series_create_activates_group(self):
        url = '/api/activity-series/'
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[0, 1]  # Monday and Tuesday
        )
        start_date = self.group.timezone.localize(datetime.now().replace(hour=20, minute=0))
        activity_series_data = {
            'activity_type': self.activity_type.id,
            'max_participants': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'start_date': start_date
        }
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        self.client.post(url, activity_series_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)


class TestActivitySeriesChangeAPI(APITestCase, ExtractPaginationMixin):
    """
    This is an integration test for the activity-series API with pre-created series
    """
    def setUp(self):
        self.now = timezone.now()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.series = ActivitySeriesFactory(max_participants=3, place=self.place)

    def test_change_max_participants_for_series(self):
        "should change all future instances (except for individually changed ones), but not past ones"
        url = '/api/activity-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(url, {'max_participants': 99})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_participants'], 99)

        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['max_participants'], 99)

    def test_change_series_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        url = '/api/activity-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        self.client.patch(url, {'max_participants': 99})
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_change_start_time(self):
        self.client.force_login(user=self.member)
        # get original times
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change times
        url = '/api/activity-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(
            self.series.start_date, relativedelta(hours=2, minutes=20), self.group.timezone
        )
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting activities
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for response_activity, old_date in zip(response.data, original_dates):
            self.assertEqual(
                parse(response_activity['date'][0]),
                shift_date_in_local_time(old_date, relativedelta(hours=2, minutes=20), self.group.timezone)
            )

    def test_change_start_date_to_future(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change dates
        url = '/api/activity-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(self.series.start_date, relativedelta(days=5), self.group.timezone)
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting activities
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for response_activity, old_date in zip_longest(response.data, original_dates):
            self.assertEqual(
                parse(response_activity['date'][0]),
                shift_date_in_local_time(old_date, relativedelta(days=5), self.group.timezone)
            )

    def test_change_start_date_to_past(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change dates
        url = '/api/activity-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(self.series.start_date, relativedelta(days=-5), self.group.timezone)
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting activities
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # shifting 5 days to the past is similar to shifting 2 days to the future
        for response_activity, old_date in zip_longest(response.data, original_dates):
            new_date = shift_date_in_local_time(old_date, relativedelta(days=2), self.group.timezone)
            if new_date > self.now + relativedelta(weeks=self.place.weeks_in_advance):
                # date too far in future
                self.assertIsNone(response_activity)
            else:
                self.assertEqual(parse(response_activity['date'][0]), new_date)

    def test_set_end_date(self):
        self.client.force_login(user=self.member)
        # change rule
        url = '/api/activity-series/{}/'.format(self.series.id)
        rule = 'FREQ=WEEKLY;UNTIL={}'.format((self.now + relativedelta(days=8)).strftime('%Y%m%dT%H%M%S'))
        response = self.client.patch(url, {'rule': rule})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['rule'], rule)

        # compare resulting activities
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2, response.data)

    def test_set_end_date_with_timezone(self):
        self.client.force_login(user=self.member)
        url = '/api/activity-series/{}/'.format(self.series.id)
        rule = 'FREQ=WEEKLY;UNTIL={}+0100'.format((self.now + relativedelta(days=8)).strftime('%Y%m%dT%H%M%S'))
        response = self.client.patch(url, {'rule': rule})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_set_end_date_with_users_have_joined_activity(self):
        self.client.force_login(user=self.member)
        self.series.activities.last().add_participant(self.member)
        # change rule
        url = '/api/activity-series/{}/'.format(self.series.id)
        rule = rrulestr(self.series.rule, dtstart=self.now) \
            .replace(until=self.now)
        response = self.client.patch(url, {
            'rule': str(rule),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['rule'], str(rule))

        # compare resulting activities
        url = '/api/activities/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1, response.data)

    def test_disable_activity_series(self):
        "the series should get removed, empty upcoming activities disabled, non-empty activities kept"
        self.client.force_login(user=self.member)
        joined_activity = self.series.activities.last()
        joined_activity.add_participant(self.member)

        url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        url = '/api/activities/'
        response = self.get_results(url, {'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        empty_activities = [p for p in response.data if len(p['participants']) == 0]
        self.assertEqual(empty_activities, [])

        url = '/api/activities/{}/'.format(joined_activity.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['participants'], [self.member.id])
        self.assertFalse(response.data['is_disabled'])

    def test_change_max_participants_to_invalid_number_fails(self):
        self.client.force_login(user=self.member)
        url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'max_participants': -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_set_invalid_place_fails(self):
        original_place = self.series.place
        unrelated_place = PlaceFactory()

        self.client.force_login(user=self.member)
        url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'place': unrelated_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['place'], original_place.id)
        self.series.refresh_from_db()
        self.assertEqual(self.series.place.id, original_place.id)

    def test_set_multiple_rules_fails(self):
        self.client.force_login(user=self.member)
        url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'rule': 'RRULE:FREQ=WEEKLY;BYDAY=MO\nRRULE:FREQ=MONTHLY'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'rule': ['Only single recurrence rules are allowed.']})

    def test_keep_changes_to_max_participants(self):
        self.client.force_login(user=self.member)
        activity_under_test = self.series.activities.first()
        url = '/api/activities/{}/'.format(activity_under_test.id)

        # change setting of activity
        response = self.client.patch(url, {'max_participants': 666})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_participants'], 666)

        # run regular update command of series
        self.series.update_activities()

        # check if changes persist
        url = '/api/activities/{}/'.format(activity_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_participants'], 666)

        # modify series max_participants
        series_url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.patch(series_url, {'max_participants': 20})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # check if changes persist
        url = '/api/activities/{}/'.format(activity_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_participants'], 666)

    def test_keep_changes_to_description(self):
        self.client.force_login(user=self.member)
        activity_under_test = self.series.activities.first()
        url = '/api/activities/{}/'.format(activity_under_test.id)

        # change setting of activity
        response = self.client.patch(url, {'description': 'asdf'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

        # run regular update command of series
        self.series.update_activities()

        # check if changes persist
        url = '/api/activities/{}/'.format(activity_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

        # modify series description
        series_url = '/api/activity-series/{}/'.format(self.series.id)
        response = self.client.patch(series_url, {'description': 'new series description'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # check if changes persist
        url = '/api/activities/{}/'.format(activity_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

    def test_invalid_rule_fails(self):
        url = '/api/activity-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(url, {'rule': 'FREQ=WEEKLY;BYDAY='})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_keeps_joined_activities(self):
        # join activities
        [p.add_participant(self.member) for p in self.series.activities.all()]

        # change series rule to add another day
        today = self.now.astimezone(self.group.timezone).weekday()
        tomorrow = shift_date_in_local_time(self.now, relativedelta(days=1),
                                            self.group.timezone).astimezone(self.group.timezone).weekday()
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[
                today,
                tomorrow,
            ],
        )
        series_url = '/api/activity-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(series_url, {
            'rule': str(recurrence),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.series.refresh_from_db()

        response = self.client.get('/api/activities/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # self.assertEqual([parse(p['date'][0]) for p in response.data['results']], [
        #     shift_date_in_local_time(self.series.start_date, delta, self.group.timezone) for delta in (
        #         relativedelta(days=0),
        #         relativedelta(days=1),
        #         relativedelta(days=7),
        #         relativedelta(days=8),
        #         relativedelta(days=14),
        #         relativedelta(days=15),
        #         relativedelta(days=21),
        #         relativedelta(days=22),
        #     )
        # ])
        self.assertEqual(
            [p['participants'] for p in response.data['results']],
            list(interleave(
                [[self.member.id] for _ in range(4)],
                [[] for _ in range(4)],
            )),
        )

    def test_removes_empty_leftover_activities_when_reducing_weeks_in_advance(self):
        # join one activity
        joined_activity = self.series.activities.first()
        joined_activity.add_participant(self.member)

        # change weeks_in_advance
        place_url = '/api/places/{}/'.format(self.place.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(place_url, {
            'weeks_in_advance': 1,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.get_results('/api/activities/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], joined_activity.id)
        self.assertEqual(response.data[0]['participants'], [self.member.id])

    def test_cannot_move_activities_in_a_series(self):
        self.client.force_login(user=self.member)
        activity = self.series.activities.last()

        response = self.client.patch(
            '/api/activities/{}/'.format(activity.id),
            {
                'date': (activity.date + relativedelta(weeks=7)).as_list(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('You can\'t move activities', response.data['date'][0])

    def test_cannot_change_activity_has_duration_in_a_series(self):
        self.client.force_login(user=self.member)
        activity = self.series.activities.last()

        response = self.client.patch(
            '/api/activities/{}/'.format(activity.id),
            {'has_duration': True},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            'You cannot modify the duration of activities that are part of a series', response.data['has_duration'][0]
        )


class TestActivitySeriesAPIAuth(APITestCase):
    """ Testing actions that are forbidden """
    def setUp(self):
        self.url = '/api/activity-series/'
        self.series = ActivitySeriesFactory()
        self.series_url = '/api/activity-series/{}/'.format(self.series.id)
        self.non_member = UserFactory()
        self.series_data = {'place': self.series.place.id, 'rule': 'FREQ=WEEKLY', 'start_date': timezone.now()}

    def test_create_as_anonymous_fails(self):
        response = self.client.post(self.url, self.series_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.post(self.url, self.series_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.series.place.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.url, self.series_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_as_anonymous_fails(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_list_as_nonmember_returns_empty_list(self):
        self.client.force_login(self.non_member)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 0)

    def test_get_as_anonymous_fails(self):
        response = self.client.get(self.series_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_get_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.get(self.series_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_patch_as_anonymous_fails(self):
        response = self.client.patch(self.series_url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_patch_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.patch(self.series_url, {})
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_patch_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.series.place.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.series_url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_delete_as_anonymous_fails(self):
        response = self.client.delete(self.series_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_delete_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.delete(self.series_url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_delete_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.series.place.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.delete(self.series_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
