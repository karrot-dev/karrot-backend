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

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupStatus
from foodsaving.pickups.factories import PickupDateSeriesFactory
from foodsaving.places.factories import PlaceFactory
from foodsaving.tests.utils import ExtractPaginationMixin
from foodsaving.users.factories import UserFactory


def shift_date_in_local_time(old_date, delta, tz):
    # keeps local time equal, even through daylight saving time transitions
    # e.g. 20:00 + 1 day is always 20:00 on the next day, even if UTC offset changes
    old_date = old_date.astimezone(tz).replace(tzinfo=None)
    new_date = old_date + delta
    return tz.localize(new_date).astimezone(tzlocal())


class TestPickupDateSeriesCreationAPI(APITestCase, ExtractPaginationMixin):
    """
    This is an integration test for the pickup-date-series API
    """

    def setUp(self):
        self.maxDiff = None
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)

    def test_create_and_get_recurring_series(self):
        self.maxDiff = None
        url = '/api/pickup-date-series/'
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[0, 1]  # Monday and Tuesday
        )
        start_date = self.group.timezone.localize(datetime.now().replace(hour=20, minute=0))
        pickup_series_data = {
            'max_collectors': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'start_date': start_date
        }
        start_date = start_date.replace(second=0, microsecond=0)
        self.client.force_login(user=self.member)
        response = self.client.post(url, pickup_series_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        series_id = response.data['id']
        self.assertEqual(parse(response.data['start_date']), start_date)
        del response.data['id']
        del response.data['start_date']
        del response.data['dates_preview']
        expected_series_data = {
            'max_collectors': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'description': '',
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

        url = '/api/pickup-dates/'
        created_pickup_dates = []
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
            created_pickup_dates.append({
                'max_collectors': 5,
                'series': series_id,
                'collectors': [],
                'place': self.place.id,
                'description': '',
                'feedback_given_by': [],
                'is_disabled': False,
            })
        self.assertEqual(response.data, created_pickup_dates, response.data)

    def test_pickup_series_create_activates_group(self):
        url = '/api/pickup-date-series/'
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[0, 1]  # Monday and Tuesday
        )
        start_date = self.group.timezone.localize(datetime.now().replace(hour=20, minute=0))
        pickup_series_data = {
            'max_collectors': 5,
            'place': self.place.id,
            'rule': str(recurrence),
            'start_date': start_date
        }
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        self.client.force_login(user=self.member)
        self.client.post(url, pickup_series_data, format='json')
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)


class TestPickupDateSeriesChangeAPI(APITestCase, ExtractPaginationMixin):
    """
    This is an integration test for the pickup-date-series API with pre-created series
    """

    def setUp(self):
        self.now = timezone.now()
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.series = PickupDateSeriesFactory(max_collectors=3, place=self.place)

    def test_change_max_collectors_for_series(self):
        "should change all future instances (except for individually changed ones), but not past ones"
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(url, {'max_collectors': 99})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_collectors'], 99)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for _ in response.data:
            self.assertEqual(_['max_collectors'], 99)

    def test_change_series_activates_group(self):
        self.group.status = GroupStatus.INACTIVE.value
        self.group.save()
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        self.client.patch(url, {'max_collectors': 99})
        self.group.refresh_from_db()
        self.assertEqual(self.group.status, GroupStatus.ACTIVE.value)

    def test_change_start_time(self):
        self.client.force_login(user=self.member)
        # get original times
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change times
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(
            self.series.start_date, relativedelta(hours=2, minutes=20), self.group.timezone
        )
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting pickups
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for response_pickup, old_date in zip(response.data, original_dates):
            self.assertEqual(
                parse(response_pickup['date'][0]),
                shift_date_in_local_time(old_date, relativedelta(hours=2, minutes=20), self.group.timezone)
            )

    def test_change_start_date_to_future(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change dates
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(self.series.start_date, relativedelta(days=5), self.group.timezone)
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting pickups
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        for response_pickup, old_date in zip_longest(response.data, original_dates):
            self.assertEqual(
                parse(response_pickup['date'][0]),
                shift_date_in_local_time(old_date, relativedelta(days=5), self.group.timezone)
            )

    def test_change_start_date_to_past(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date'][0]) for _ in response.data]

        # change dates
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        new_startdate = shift_date_in_local_time(self.series.start_date, relativedelta(days=-5), self.group.timezone)
        response = self.client.patch(url, {'start_date': new_startdate.isoformat()})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['start_date']), new_startdate)

        # compare resulting pickups
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # shifting 5 days to the past is similar to shifting 2 days to the future
        for response_pickup, old_date in zip_longest(response.data, original_dates):
            new_date = shift_date_in_local_time(old_date, relativedelta(days=2), self.group.timezone)
            if new_date > self.now + relativedelta(weeks=self.place.weeks_in_advance):
                # date too far in future
                self.assertIsNone(response_pickup)
            else:
                self.assertEqual(parse(response_pickup['date'][0]), new_date)

    def test_set_end_date(self):
        self.client.force_login(user=self.member)
        # change rule
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        rule = rrulestr(self.series.rule, dtstart=self.now) \
            .replace(until=self.now + relativedelta(days=8))
        response = self.client.patch(url, {'rule': str(rule)})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['rule'], str(rule))

        # compare resulting pickups
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 2, response.data)

    def test_set_end_date_with_users_have_joined_pickup(self):
        self.client.force_login(user=self.member)
        self.series.pickup_dates.last().add_collector(self.member)
        # change rule
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        rule = rrulestr(self.series.rule, dtstart=self.now) \
            .replace(until=self.now)
        response = self.client.patch(url, {
            'rule': str(rule),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['rule'], str(rule))

        # compare resulting pickups
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data), 1, response.data)

    def test_disable_pickup_series(self):
        "the series should get removed, empty upcoming pickups disabled, non-empty pickups kept"
        self.client.force_login(user=self.member)
        joined_pickup = self.series.pickup_dates.last()
        joined_pickup.add_collector(self.member)

        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT, response.data)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        empty_pickups = [p for p in response.data if len(p['collectors']) == 0]
        self.assertEqual(empty_pickups, [])

        url = '/api/pickup-dates/{}/'.format(joined_pickup.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['collectors'], [self.member.id])
        self.assertFalse(response.data['is_disabled'])

    def test_change_max_collectors_to_invalid_number_fails(self):
        self.client.force_login(user=self.member)
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'max_collectors': -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_set_invalid_place_fails(self):
        original_place = self.series.place
        unrelated_place = PlaceFactory()

        self.client.force_login(user=self.member)
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'place': unrelated_place.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['place'], original_place.id)
        self.series.refresh_from_db()
        self.assertEqual(self.series.place.id, original_place.id)

    def test_set_multiple_rules_fails(self):
        self.client.force_login(user=self.member)
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'rule': 'RRULE:FREQ=WEEKLY;BYDAY=MO\nRRULE:FREQ=MONTHLY'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)
        self.assertEqual(response.data, {'rule': ['Only single recurrence rules are allowed.']})

    def test_keep_changes_to_max_collectors(self):
        self.client.force_login(user=self.member)
        pickup_under_test = self.series.pickup_dates.first()
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)

        # change setting of pickup
        response = self.client.patch(url, {'max_collectors': 666})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_collectors'], 666)

        # run regular update command of series
        self.series.update_pickups()

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_collectors'], 666)

        # modify series max_collectors
        series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(series_url, {'max_collectors': 20})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_collectors'], 666)

    def test_keep_changes_to_description(self):
        self.client.force_login(user=self.member)
        pickup_under_test = self.series.pickup_dates.first()
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)

        # change setting of pickup
        response = self.client.patch(url, {'description': 'asdf'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

        # run regular update command of series
        self.series.update_pickups()

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

        # modify series description
        series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(series_url, {'description': 'new series description'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

    def test_invalid_rule_fails(self):
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(url, {'rule': 'FREQ=WEEKLY;BYDAY='})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_keeps_joined_pickups(self):
        # join pickups
        [p.add_collector(self.member) for p in self.series.pickup_dates.all()]

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
        series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(series_url, {
            'rule': str(recurrence),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.series.refresh_from_db()

        response = self.client.get('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([parse(p['date'][0]) for p in response.data['results']], [
            shift_date_in_local_time(self.series.start_date, delta, self.group.timezone) for delta in (
                relativedelta(days=0),
                relativedelta(days=1),
                relativedelta(days=7),
                relativedelta(days=8),
                relativedelta(days=14),
                relativedelta(days=15),
                relativedelta(days=21),
                relativedelta(days=22),
            )
        ])
        self.assertEqual(
            [p['collectors'] for p in response.data['results']],
            list(interleave(
                [[self.member.id] for _ in range(4)],
                [[] for _ in range(4)],
            )),
        )

    def test_removes_empty_leftover_pickups_when_reducing_weeks_in_advance(self):
        # join one pickup
        joined_pickup = self.series.pickup_dates.first()
        joined_pickup.add_collector(self.member)

        # change weeks_in_advance
        place_url = '/api/places/{}/'.format(self.place.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(place_url, {
            'weeks_in_advance': 1,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.get_results('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['id'], joined_pickup.id)
        self.assertEqual(response.data[0]['collectors'], [self.member.id])

    def test_cannot_move_pickups_in_a_series(self):
        self.client.force_login(user=self.member)
        pickup = self.series.pickup_dates.last()

        response = self.client.patch(
            '/api/pickup-dates/{}/'.format(pickup.id),
            {
                'date': (pickup.date + relativedelta(weeks=7)).as_list(),
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('You can\'t move pickups', response.data['date'][0])


class TestPickupDateSeriesAPIAuth(APITestCase):
    """ Testing actions that are forbidden """

    def setUp(self):
        self.url = '/api/pickup-date-series/'
        self.series = PickupDateSeriesFactory()
        self.series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
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
