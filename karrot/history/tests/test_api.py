from dateutil.parser import parse
from dateutil.relativedelta import relativedelta
from django.utils import timezone
from rest_framework.reverse import reverse
from rest_framework.test import APITestCase

from karrot.groups.factories import GroupFactory
from karrot.groups.models import GroupMembership
from karrot.history.models import History
from karrot.activities.factories import ActivityFactory, \
    ActivitySeriesFactory, ActivityTypeFactory
from karrot.activities.models import Activity, to_range
from karrot.places.factories import PlaceFactory
from karrot.tests.utils import ExtractPaginationMixin
from karrot.users.factories import UserFactory

history_url = '/api/history/'


class TestHistoryAPICreateGroup(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_create_group(self):
        self.client.force_login(self.member)
        self.client.post('/api/groups/', {'name': 'xyzabc', 'timezone': 'Europe/Berlin'})
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'GROUP_CREATE')


class TestHistoryAPIOrdering(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_ordering(self):
        self.client.force_login(self.member)
        self.client.post('/api/groups/', {'name': 'Group 1', 'timezone': 'Europe/Berlin'})
        self.client.post('/api/groups/', {'name': 'Group 2', 'timezone': 'Europe/Berlin'})
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['payload']['name'], 'Group 2')


class TestHistoryAPIWithExistingGroup(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member], is_open=True)
        self.group_url = '/api/groups/{}/'.format(self.group.id)

    def test_modify_group(self):
        self.client.force_login(self.member)
        self.client.patch(self.group_url, {'name': 'something new'})
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'GROUP_MODIFY')
        self.assertEqual(response.data[0]['payload']['name'], 'something new')

    def test_dont_modify_group(self):
        self.client.force_login(self.member)
        self.client.patch(self.group_url, {'name': self.group.name})
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 0)

    def test_join_group(self):
        user = UserFactory()
        self.client.force_login(user)
        self.client.post(self.group_url + 'join/')
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'GROUP_JOIN')

    def test_leave_group(self):
        user = UserFactory()
        GroupMembership.objects.create(group=self.group, user=user)
        self.client.force_login(user)
        self.client.post(self.group_url + 'leave/')

        self.client.force_login(self.member)
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'GROUP_LEAVE')

    def test_member_becomes_editor(self):
        user = UserFactory()
        GroupMembership.objects.create(group=self.group, user=user)
        url = reverse('group-trust-user', args=(self.group.id, user.id))
        self.client.force_login(self.member)

        self.client.post(url)

        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'MEMBER_BECAME_EDITOR')

    def test_create_place(self):
        self.client.force_login(self.member)
        self.client.post(
            '/api/places/', {
                'name': 'xyzabc',
                'group': self.group.id,
                'place_type': self.group.place_types.first().id,
                'status': self.group.place_statuses.first().id
            }
        )
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'STORE_CREATE')


class TestHistoryAPIWithExistingPlace(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.place_url = '/api/places/{}/'.format(self.place.id)
        self.activity_type = ActivityTypeFactory(group=self.group)

    def test_modify_place(self):
        self.client.force_login(self.member)
        self.client.patch(
            self.place_url,
            {
                'name': 'newnew',  # new value
                'description': self.place.description  # no change
            }
        )
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 1, response.data)
        history = response.data[0]
        self.assertEqual(history['typus'], 'STORE_MODIFY')
        self.assertEqual(history['payload']['name'], 'newnew')

    def test_dont_modify_place(self):
        self.client.force_login(self.member)
        self.client.patch(self.place_url, {'name': self.place.name})
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 0)

    def test_create_activity(self):
        self.client.force_login(self.member)
        self.client.post(
            '/api/activities/', {
                'activity_type': self.activity_type.id,
                'date': to_range(timezone.now() + relativedelta(days=1)).as_list(),
                'place': self.place.id
            },
            format='json'
        )
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_CREATE')

    def test_create_series(self):
        self.client.force_login(self.member)
        self.client.post(
            '/api/activity-series/', {
                'activity_type': self.activity_type.id,
                'start_date': timezone.now(),
                'rule': 'FREQ=WEEKLY',
                'place': self.place.id
            }
        )
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'SERIES_CREATE')


class TestHistoryAPIWithExistingActivities(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place)
        self.activity_url = '/api/activities/{}/'.format(self.activity.id)
        self.series = ActivitySeriesFactory(place=self.place)
        self.series_url = '/api/activity-series/{}/'.format(self.series.id)

    def test_modify_activity(self):
        self.client.force_login(self.member)
        self.client.patch(self.activity_url, {'max_participants': '11'})
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_MODIFY')
        self.assertEqual(response.data[0]['payload']['max_participants'], '11')

    def test_dont_modify_activity(self):
        self.client.force_login(self.member)
        self.client.patch(self.activity_url, {'date': self.activity.date.as_list()}, format='json')
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 0, response.data)

    def test_modify_series(self):
        self.client.force_login(self.member)
        self.client.patch(self.series_url, {'max_participants': '11'})
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'SERIES_MODIFY')
        self.assertEqual(response.data[0]['payload']['max_participants'], '11')

    def test_dont_modify_series(self):
        self.client.force_login(self.member)
        self.client.patch(self.series_url, {'rule': self.series.rule})
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 0, response.data)

    def test_delete_series(self):
        self.client.force_login(self.member)
        self.client.delete(self.series_url)
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'SERIES_DELETE')
        self.assertEqual(response.data[0]['payload']['rule'], self.series.rule)

    def test_join_activity(self):
        self.client.force_login(self.member)
        self.client.post(self.activity_url + 'add/')
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_JOIN')
        self.assertEqual(parse(response.data[0]['payload']['date'][0]), self.activity.date.start)

    def test_leave_activity(self):
        self.client.force_login(self.member)
        self.activity.add_participant(self.member)
        self.client.post(self.activity_url + 'remove/')
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_LEAVE')
        self.assertEqual(parse(response.data[0]['payload']['date'][0]), self.activity.date.start)

    def test_disable_activity(self):
        self.client.force_login(self.member)
        History.objects.all().delete()

        self.client.patch(self.activity_url, {'is_disabled': True})

        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_DISABLE')

    def test_enable_activity(self):
        self.activity.is_disabled = True
        self.activity.save()
        self.client.force_login(self.member)
        History.objects.all().delete()

        self.client.patch(self.activity_url, {'is_disabled': False})

        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_ENABLE')


class TestHistoryAPIWithDoneActivity(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1)))
        self.activity.add_participant(self.member)
        Activity.objects.process_finished_activities()

    def test_activity_done(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_DONE')
        self.assertLess(parse(response.data[0]['date']), timezone.now() - relativedelta(hours=22))

    def test_filter_activity_done(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url, {'typus': 'ACTIVITY_DONE'})
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_DONE')
        response = self.get_results(history_url, {'typus': 'GROUP_JOIN'})  # unrelated event should give no result
        self.assertEqual(len(response.data), 0)


class TestHistoryAPIWithMissedActivity(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1)))
        # No one joined the activity
        Activity.objects.process_finished_activities()

    def test_activity_missed(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url)
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_MISSED')
        self.assertLess(parse(response.data[0]['date']), timezone.now() - relativedelta(hours=22))

    def test_filter_activity_missed(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url, {'typus': 'ACTIVITY_MISSED'})
        self.assertEqual(response.data[0]['typus'], 'ACTIVITY_MISSED')
        response = self.get_results(history_url, {'typus': 'GROUP_JOIN'})  # unrelated event should give no result
        self.assertEqual(len(response.data), 0)


class TestHistoryAPIActivityForInactivePlace(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group, status=self.group.place_statuses.get(name='Archived'))
        self.activity = ActivityFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1)))
        self.activity.add_participant(self.member)

        ActivityFactory(place=self.place, date=to_range(timezone.now() - relativedelta(days=1), minutes=30))
        Activity.objects.process_finished_activities()

    def test_no_activity_done_for_inactive_place(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url, {'typus': 'ACTIVITY_DONE'})
        self.assertEqual(len(response.data), 0)

    def test_no_activity_missed_for_inactive_place(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url, {'typus': 'ACTIVITY_MISSED'})
        self.assertEqual(len(response.data), 0)


class TestHistoryAPIWithDisabledActivity(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()
        self.group = GroupFactory(members=[self.member])
        self.place = PlaceFactory(group=self.group)
        self.activity = ActivityFactory(
            place=self.place,
            date=to_range(timezone.now() - relativedelta(days=1)),
            is_disabled=True,
        )
        Activity.objects.process_finished_activities()

    def test_no_history_for_disabled_activity(self):
        self.client.force_login(self.member)
        response = self.get_results(history_url)
        self.assertEqual(len(response.data), 0)


class TestHistoryAPIDateFiltering(APITestCase, ExtractPaginationMixin):
    def setUp(self):
        self.member = UserFactory()

    def test_filter_by_date(self):
        self.client.force_login(self.member)

        # change the group
        self.client.post('/api/groups/', {'name': 'xyzabc', 'timezone': 'Europe/Berlin'})

        # filter by date
        now = timezone.now().isoformat()
        response = self.get_results(history_url, data={'date_before': now})
        self.assertEqual(len(response.data), 1)
        response = self.get_results(history_url + '?date_before=' + now)
        self.assertEqual(len(response.data), 1)
        response = self.get_results(history_url, data={'date_after': now})
        response = self.get_results(history_url, data={'date_after': now})
        self.assertEqual(len(response.data), 0)
