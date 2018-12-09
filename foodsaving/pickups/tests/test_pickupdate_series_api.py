from itertools import zip_longest

from dateutil import rrule
from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from dateutil.rrule import rrulestr
from dateutil.tz import tzlocal
from django.utils import timezone
from django.utils.datetime_safe import datetime
from freezegun import freeze_time
from more_itertools import interleave
from rest_framework import status
from rest_framework.test import APITestCase

from foodsaving.groups.factories import GroupFactory
from foodsaving.groups.models import GroupStatus
from foodsaving.pickups.factories import PickupDateSeriesFactory
from foodsaving.stores.factories import StoreFactory
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
        self.store = StoreFactory(group=self.group)

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
            'store': self.store.id,
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
        expected_series_data = {
            'max_collectors': 5,
            'store': self.store.id,
            'rule': str(recurrence),
            'description': '',
            'last_changed_message': '',
            'last_changed_by': self.member.id,
        }
        self.assertEqual(response.data, expected_series_data)

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        for _ in response.data:
            self.assertEqual(parse(_['start_date']), start_date)
            del _['id']
            del _['start_date']
        self.assertEqual(response.data, [expected_series_data])

        response = self.client.get(url + str(series_id) + '/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(parse(response.data['start_date']), start_date)
        del response.data['id']
        del response.data['start_date']
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
            self.assertEqual(parse(response_data_item['date']), expected_date, response_data_item['date'])

        # verify non-date fields, don't need parsing
        for _ in response.data:
            del _['id']
            del _['date']
            del _['feedback_due']
        for _ in dates_list:
            created_pickup_dates.append({
                'max_collectors': 5,
                'series': series_id,
                'collector_ids': [],
                'store': self.store.id,
                'description': '',
                'feedback_given_by': [],
                'last_changed_by': self.member.id,
                'last_changed_message': '',
                'is_cancelled': False,
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
            'store': self.store.id,
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
        self.store = StoreFactory(group=self.group)
        self.series = PickupDateSeriesFactory(max_collectors=3, store=self.store)

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
        original_dates = [parse(_['date']) for _ in response.data]

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
                parse(response_pickup['date']),
                shift_date_in_local_time(old_date, relativedelta(hours=2, minutes=20), self.group.timezone)
            )

    def test_change_start_date_to_future(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date']) for _ in response.data]

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
                parse(response_pickup['date']),
                shift_date_in_local_time(old_date, relativedelta(days=5), self.group.timezone)
            )

    def test_change_start_date_to_past(self):
        self.client.force_login(user=self.member)
        # get original dates
        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        original_dates = [parse(_['date']) for _ in response.data]

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
            if new_date > self.now + relativedelta(weeks=self.store.weeks_in_advance):
                # date too far in future
                self.assertIsNone(response_pickup)
            else:
                self.assertEqual(parse(response_pickup['date']), new_date)

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

    # TODO: allow similar functionality through "cancel" endpoint
    # def test_set_end_date_with_users_have_joined_pickup(self):
    #     self.client.force_login(user=self.member)
    #     self.series.pickup_dates.last().add_collector(self.member)
    #     # change rule
    #     url = '/api/pickup-date-series/{}/'.format(self.series.id)
    #     rule = rrulestr(self.series.rule, dtstart=self.now) \
    #         .replace(until=self.now)
    #     response = self.client.patch(url, {
    #         'rule': str(rule),
    #         'last_changed_message': 'hi',
    #     })
    #     self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
    #     self.assertEqual(response.data['rule'], str(rule))
    #
    #     # compare resulting pickups
    #     url = '/api/pickup-dates/'
    #     response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
    #     self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
    #     self.assertEqual(len(response.data), 1, response.data)

    def test_cancel_pickup_series(self):
        "the series should get removed, all upcoming pickups cancelled"
        self.client.force_login(user=self.member)
        joined_pickup = self.series.pickup_dates.last()
        joined_pickup.add_collector(self.member)

        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

        url = '/api/pickup-dates/'
        response = self.get_results(url, {'series': self.series.id, 'date_min': self.now})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

        url = '/api/pickup-dates/{}/'.format(joined_pickup.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['collector_ids'], [
            self.member.id,
        ])
        self.assertFalse(response.data['is_cancelled'])

    def test_change_max_collectors_to_invalid_number_fails(self):
        self.client.force_login(user=self.member)
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'max_collectors': -1})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_set_invalid_store_fails(self):
        original_store = self.series.store
        unrelated_store = StoreFactory()

        self.client.force_login(user=self.member)
        url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(url, {'store': unrelated_store.id})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['store'], original_store.id)
        self.series.refresh_from_db()
        self.assertEqual(self.series.store.id, original_store.id)

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
        self.series.add_new_pickups()

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['max_collectors'], 666)

    def test_keep_changes_to_date(self):
        self.client.force_login(user=self.member)
        pickup_under_test = self.series.pickup_dates.first()
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)

        # change setting of pickup
        target_date = timezone.now() + relativedelta(hours=2)
        response = self.client.patch(url, {'date': target_date})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['date']), target_date)

        # run regular update command of series
        self.series.add_new_pickups()

        # check if changes persist
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(parse(response.data['date']), target_date)

    def test_keep_changes_to_description(self):
        self.client.force_login(user=self.member)
        pickup_under_test = self.series.pickup_dates.first()
        url = '/api/pickup-dates/{}/'.format(pickup_under_test.id)

        # change setting of pickup
        response = self.client.patch(url, {'description': 'asdf'})
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['description'], 'asdf')

        # run regular update command of series
        self.series.add_new_pickups()

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

    def test_keeps_moved_pickup(self):
        # move pickup via API
        pickup = self.series.pickup_dates.first()
        pickup_url = '/api/pickup-dates/{}/'.format(pickup.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(pickup_url, {
            'date': pickup.date + relativedelta(days=8),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # run update
        self.series.add_new_pickups()

        response = self.client.get('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([parse(p['date']) for p in response.data['results']], [
            shift_date_in_local_time(self.series.start_date, delta, self.group.timezone) for delta in (
                relativedelta(days=7),
                relativedelta(days=8),
                relativedelta(days=14),
                relativedelta(days=21),
            )
        ])

    def test_cancels_moved_pickup_on_series_change(self):
        # move pickup
        pickup = self.series.pickup_dates.first()
        pickup_url = '/api/pickup-dates/{}/'.format(pickup.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(pickup_url, {
            'date': pickup.date + relativedelta(days=8),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # change series rule
        series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        response = self.client.patch(series_url, {
            'start_date': self.series.start_date + relativedelta(hours=2),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.series.refresh_from_db()

        response = self.client.get('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([parse(p['date']) for p in response.data['results']], [
            shift_date_in_local_time(self.series.start_date, delta, self.group.timezone) for delta in (
                relativedelta(days=0),
                relativedelta(days=7),
                relativedelta(days=14),
                relativedelta(days=21),
            )
        ])

    def test_cancels_nonmatching_joined_pickups(self):
        # join pickups
        [p.add_collector(self.member) for p in self.series.pickup_dates.all()]

        # change series rule
        series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(series_url, {
            'start_date': self.series.start_date + relativedelta(days=1),
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.series.refresh_from_db()

        response = self.client.get('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([parse(p['date']) for p in response.data['results']], [
            shift_date_in_local_time(self.series.start_date, delta, self.group.timezone) for delta in (
                relativedelta(days=0),
                relativedelta(days=7),
                relativedelta(days=14),
                relativedelta(days=21),
            )
        ])
        self.assertEqual([p['collector_ids'] for p in response.data['results']], [[] for _ in range(4)])

    def test_keeps_matching_joined_pickups(self):
        self.maxDiff = None
        # join pickups
        [p.add_collector(self.member) for p in self.series.pickup_dates.all()]

        # change series rule to add another day
        recurrence = rrule.rrule(
            freq=rrule.WEEKLY,
            byweekday=[
                self.now.weekday(),
                (self.now + relativedelta(days=1)).weekday(),
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
        self.assertEqual([parse(p['date']) for p in response.data['results']], [
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
            [p['collector_ids'] for p in response.data['results']],
            list(interleave(
                [[self.member.id] for _ in range(4)],
                [[] for _ in range(4)],
            )),
        )

    def test_cancels_leftover_pickups_when_reducing_weeks_in_advance(self):
        # join pickups
        [p.add_collector(self.member) for p in self.series.pickup_dates.all()]

        # change weeks_in_advance
        store_url = '/api/stores/{}/'.format(self.store.id)
        self.client.force_login(user=self.member)
        response = self.client.patch(store_url, {
            'weeks_in_advance': 1,
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get('/api/pickup-dates/?series={}'.format(self.series.id))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual([parse(p['date']) for p in response.data['results']], [
            shift_date_in_local_time(self.series.start_date, delta, self.group.timezone)
            for delta in (relativedelta(days=0), )
        ])
        self.assertEqual(response.data['results'][0]['collector_ids'][0], self.member.id)

    def test_preview(self):
        self.client.force_login(user=self.member)
        with freeze_time(datetime(2018, 11, 25, tzinfo=self.group.timezone), tick=True):
            series = PickupDateSeriesFactory(store=self.store, rule='FREQ=WEEKLY;BYDAY=MO')
            series.pickup_dates.last().add_collector(self.member)
            response = self.client.post(
                '/api/pickup-date-series/{}/get_pickup_preview/'.format(series.id),
                {'rule': 'FREQ=WEEKLY;BYDAY=MO,TU'}
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual([(e['existing_pickup'] is not None, e['new_date'] is not None) for e in response.data], [
            (True, True),
            (False, True),
            (True, True),
            (False, True),
            (True, True),
            (False, True),
            (True, True),
            (False, True),
        ])
        self.assertEqual(response.data[-2]['existing_pickup']['collector_ids'], [self.member.id])


class TestPickupDateSeriesAPIAuth(APITestCase):
    """ Testing actions that are forbidden """

    def setUp(self):
        self.url = '/api/pickup-date-series/'
        self.series = PickupDateSeriesFactory()
        self.series_url = '/api/pickup-date-series/{}/'.format(self.series.id)
        self.non_member = UserFactory()
        self.series_data = {'store': self.series.store.id, 'rule': 'FREQ=WEEKLY', 'start_date': timezone.now()}

    def test_create_as_anonymous_fails(self):
        response = self.client.post(self.url, self.series_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.post(self.url, self.series_data)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_create_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.series.store.group.groupmembership_set.create(user=newcomer)
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
        self.series.store.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.patch(self.series_url, {})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_delete_as_anonymous_fails(self):
        response = self.client.post(self.series_url + 'cancel/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)

    def test_delete_as_nonmember_fails(self):
        self.client.force_login(self.non_member)
        response = self.client.post(self.series_url + 'cancel/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.data)

    def test_delete_as_newcomer_fails(self):
        newcomer = UserFactory()
        self.series.store.group.groupmembership_set.create(user=newcomer)
        self.client.force_login(user=newcomer)
        response = self.client.post(self.series_url + 'cancel/')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.data)
