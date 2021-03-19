import time

import pytz
import random
from dateutil.relativedelta import relativedelta
from django.contrib.auth import get_user
from django.core import mail
from django.core.management.base import BaseCommand
from django.http import request
from django.utils import timezone
from rest_framework.test import APIClient

from karrot.groups.models import Group, GroupMembership, GroupStatus
from karrot.groups.roles import GROUP_EDITOR
from karrot.activities.models import Activity, ActivitySeries, to_range, ActivityType
from karrot.places.models import Place, PlaceStatus, PlaceType
from karrot.users.models import User
from karrot.utils.tests.fake import faker


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--more', action='store_true', dest='more_data')
        parser.add_argument('--quick', action='store_true', dest='less_data')

    def handle(self, *args, **options):
        faker.seed_instance(int(time.time()))

        def print(*args):
            self.stdout.write(' '.join([str(_) for _ in args]))

        def print_success(*args):
            self.stdout.write(self.style.SUCCESS(' '.join(str(_) for _ in args)))

        ######################
        # Setup
        # override the allowed hosts, similar to tests
        # needs teardown at the end
        ######################

        from django.conf import settings

        def setup_environment():
            mail._BLA_original_email_backend = settings.EMAIL_BACKEND
            settings.EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
            request._BLA_original_allowed_hosts = settings.ALLOWED_HOSTS
            settings.ALLOWED_HOSTS = ['*']
            request._BLAH_original_influxdb_disable = settings.INFLUXDB_DISABLED
            settings.INFLUXDB_DISABLED = True

        def teardown_environment():
            settings.EMAIL_BACKEND = mail._BLA_original_email_backend
            settings.ALLOWED_HOSTS = request._BLA_original_allowed_hosts
            settings.INFLUXDB_DISABLED = request._BLAH_original_influxdb_disable = settings.INFLUXDB_DISABLED

        setup_environment()

        ######################
        # Helper functions
        ######################

        c = APIClient()
        groups = []
        users = []

        def login_user(id=None):
            # if no user is provided, choose a random user from the list
            if not id:
                id = random.choice(users)['id']
            u = User.objects.get(id=id)
            c.force_login(u)
            print('login as', u)
            return u

        default_password = '123'

        def make_user(verified=True):
            response = c.post(
                '/api/auth/user/', {
                    'email': str(timezone.now().microsecond) + faker.email(),
                    'password': default_password,
                    'display_name': faker.name(),
                    'description': 'I am a fake user',
                    'mobile_number': faker.phone_number()
                }
            )
            if response.status_code != 201:
                raise Exception('could not make user', response.data)
            user = response.data
            User.objects.get(id=user['id']).verify_mail()
            print('created user:', user['email'])
            return user

        def make_group(country_code='DE'):
            lat, lng, city, country, timezone = faker.local_latlng(country_code=country_code)
            response = c.post(
                '/api/groups/', {
                    'name': 'Group ' + city,
                    'description': faker.text(),
                    'timezone': 'Europe/Berlin',
                    'address': faker.street_address() + ', ' + city,
                    'latitude': lat,
                    'longitude': lng
                }
            )
            if response.status_code != 201:
                raise Exception('could not make group', response.data)
            data = response.data
            conversation = c.get('/api/groups/{}/conversation/'.format(data['id'])).data
            data['conversation'] = conversation
            print('created group: ', data['id'], data['name'])
            return data

        def modify_group(group):
            response = c.patch(
                '/api/groups/{}/'.format(group), {
                    'name': 'Group (edited) ' + faker.city(),
                    'description': faker.text(),
                }
            )
            if response.status_code != 200:
                raise Exception('could not modify group', group, response.data)
            print('modified group: ', group)
            return response.data

        def join_group(group):
            # get_user expects a Request, but the test client seems good enough as it has a session member variable
            user = get_user(c)
            Group.objects.get(id=group).add_member(user)

            # make editor
            membership = GroupMembership.objects.get(user=user, group_id=group)
            membership.roles.append(GROUP_EDITOR)
            membership.save()

            print('joined group {}'.format(group))
            return

        def apply_to_group(group):
            response = c.post('/api/applications/', {
                'answers': faker.text(),
                'group': group,
            })
            if response.status_code != 201:
                raise Exception('could not apply to group', group, response.data)

            print('applied to group {}'.format(group))
            return response.data

        def trust_user_in_group(user, group):
            response = c.post('/api/groups/{}/users/{}/trust/'.format(group, user))
            if response.status_code != 200:
                raise Exception('could not trust user', user, response.data)

            print('trusted user {} in group {}'.format(user, group))
            return response.data

        def leave_group(group):
            response = c.post('/api/groups/{}/leave/'.format(group))
            if response.status_code != 200:
                raise Exception('could not leave group', group, response.data)
            print('left group {}'.format(group))
            return response.data

        def make_message(conversation_id):
            response = c.post('/api/messages/', {
                'content': faker.text(),
                'conversation': conversation_id,
            })
            if response.status_code != 201:
                raise Exception('could not make message', conversation_id, response.data)
            return response.data

        def make_place(group):
            response = c.post(
                '/api/places/', {
                    'name': 'Place ' + faker.name(),
                    'description': faker.text(),
                    'group': group,
                    'address': faker.street_address(),
                    'latitude': faker.latitude(),
                    'longitude': faker.longitude(),
                    'status': PlaceStatus.objects.get(group=group, name='Active').id,
                    'place_type': PlaceType.objects.get(group=group, name='Store').id,
                }
            )
            if response.status_code != 201:
                raise Exception('could not make place', response.data)
            data = response.data
            print('created place: ', data['id'], data['name'])
            return data

        def modify_place(place):
            response = c.patch(
                '/api/places/{}/'.format(place), {
                    'name': 'Place (edited) ' + faker.name(),
                    'description': faker.text(),
                }
            )
            if response.status_code != 200:
                raise Exception('could not modify place', place, response.data)
            print('modified place: ', place)
            return response.data

        def make_series(place, activity_type):
            response = c.post(
                '/api/activity-series/', {
                    'activity_type': activity_type.id,
                    'start_date': faker.date_time_between(start_date='now', end_date='+24h', tzinfo=pytz.utc),
                    'rule': 'FREQ=WEEKLY;BYDAY=MO,TU,SA',
                    'max_participants': 10,
                    'place': place
                }
            )
            if response.status_code != 201:
                raise Exception('could not make series', place, response.data)
            data = response.data
            print('created series: ', data)
            return data

        def modify_series(series):
            response = c.patch(
                '/api/activity-series/{}/'.format(series), {
                    'start_date': timezone.now().replace(hour=20),
                    'rule': 'FREQ=WEEKLY'
                }
            )
            if response.status_code != 200:
                raise Exception('could not modify series', series, response.data)
            print('modified series: ', series)
            return response.data

        def delete_series(series):
            response = c.delete('/api/activity-series/{}/'.format(series))
            if response.status_code != 204:
                raise Exception('could not delete series', series, response.status_code, response.data)
            print('deleted series: ', series)
            return response.data

        def make_activity(place, activity_type):
            date = to_range(faker.date_time_between(start_date='+2d', end_date='+7d', tzinfo=pytz.utc))
            response = c.post(
                '/api/activities/',
                {
                    'activity_type': activity_type.id,
                    'date': date.as_list(),
                    'place': place,
                    'max_participants': 10
                },
                format='json',
            )
            if response.status_code != 201:
                raise Exception('could not make activity', response.data)
            data = response.data
            p = Activity.objects.get(pk=data['id'])
            print('created activity: ', data, p.date)
            return data

        def modify_activity(activity):
            response = c.patch('/api/activities/{}/'.format(activity), {'max_participants': 3})
            if response.status_code != 200:
                raise Exception('could not modify activity', activity, response.data)
            print('modified activity: ', activity)
            return response.data

        def join_activity(activity):
            response = c.post('/api/activities/{}/add/'.format(activity))
            if response.status_code != 200:
                raise Exception('could not join activity', activity, response.data)
            print('joined activity: ', activity)
            return response.data

        def leave_activity(activity):
            response = c.post('/api/activities/{}/remove/'.format(activity))
            if response.status_code != 200:
                raise Exception('could not leave activity', activity, response.data)
            print('left activity: ', activity)
            return response.data

        def make_feedback(activity, given_by):
            response = c.post(
                '/api/feedback/', {
                    'comment': faker.text(),
                    'weight': 100.0,
                    'about': activity,
                    'given_by': given_by,
                }
            )
            if response.status_code != 201:
                raise Exception('could not make feedback', activity, response.data)
            print('created feedback: ', response.data)
            return response.data

        def random_activity_type(group_id):
            return find_activity_type(group=group_id)

        def find_activity_type(**filter_params):
            return ActivityType.objects.filter(**filter_params).order_by('?').first()

        def create_done_activity(place, user_id, activity_type):
            activity = Activity.objects.create(
                activity_type=activity_type,
                date=to_range(faker.date_time_between(start_date='-9d', end_date='-1d', tzinfo=pytz.utc), minutes=30),
                place_id=place,
                max_participants=10,
            )
            activity.add_participant(User.objects.get(pk=user_id))
            print('created done activity: ', activity)
            return activity

        ######################
        # Sample data
        ######################

        i = 0 if options['more_data'] else 2 if options['less_data'] else 1

        # these are group creators
        n_groups = (8, 3, 1)[i]
        for _ in range(n_groups):
            user = make_user()
            users.append(user)
            login_user(user['id'])
            group = make_group()
            groups.append(group)
            for _ in range(5):
                place = make_place(group['id'])
                make_series(place['id'], random_activity_type(group['id']))
                activity = make_activity(place['id'], random_activity_type(group['id']))
                join_activity(activity['id'])
                print(group['conversation'])
                make_message(group['conversation']['id'])
                done_activity = create_done_activity(
                    place['id'], user['id'],
                    find_activity_type(group=group['id'], has_feedback=True, has_feedback_weight=True)
                )
                make_feedback(done_activity.id, user['id'])

        # group members
        min_members = (6, 3, 1)[i]
        max_members = (18, 6, 2)[i]
        n_activities = (3, 2, 1)[i]
        for g in groups:
            for _ in range(random.randint(min_members, max_members)):
                user = make_user()
                users.append(user)
                login_user(user['id'])
                join_group(g['id'])
                for p in Activity.objects.filter(date__startswith__gte=timezone.now() + relativedelta(hours=1),
                                                 place__group_id=g['id']).order_by('?')[:n_activities]:
                    join_activity(p.id)

            # create group applications
            applicant = make_user()
            login_user(applicant['id'])
            User.objects.get(id=applicant['id']).verify_mail()
            apply_to_group(g['id'])

        # trust some group members
        for g in groups:
            two_users = User.objects.filter(groupmembership__group=g['id']).distinct()[:2]
            login_user(two_users[0].id)
            trust_user_in_group(two_users[1].id, g['id'])
            login_user(two_users[1].id)
            trust_user_in_group(two_users[0].id, g['id'])

        # modify
        u = login_user()
        o = Group.objects.user_is_editor(u).first()
        modify_group(o.id)

        u = login_user()
        o = Place.objects.filter(group__in=Group.objects.user_is_editor(u)).first()
        modify_place(o.id)

        u = login_user()
        o = ActivitySeries.objects.filter(place__group__in=Group.objects.user_is_editor(u)).first()
        modify_series(o.id)

        u = login_user()
        o = Activity.objects.filter(
            date__startswith__gte=timezone.now() + relativedelta(hours=1),
            place__group__in=Group.objects.user_is_editor(u)
        ).first()
        modify_activity(o.id)

        # leave
        u = login_user()
        o = Activity.objects.filter(
            date__startswith__gte=timezone.now() + relativedelta(minutes=10), participants=u
        ).first()
        leave_activity(o.id)

        # activity done
        # We join an activity and shift it back
        n_done = (5, 3, 1)[i]
        for _ in range(n_done):
            u = login_user()
            p = Activity.objects.filter(
                date__startswith__gte=timezone.now() + relativedelta(hours=1), place__group__members=u
            ).exclude(participants=u).first()
            join_activity(p.id)

            difference = timezone.now() - p.date.end + relativedelta(days=4)
            p.date -= difference
            p.save()
            print('did an activity at', p.date)
        Activity.objects.process_finished_activities()

        # delete
        u = login_user()
        o = ActivitySeries.objects.filter(place__group__in=Group.objects.user_is_editor(u)).first()
        delete_series(o.id)

        u = login_user()
        o = Group.objects.filter(members=u).first()
        leave_group(o.id)

        # Create user that is already preconfigured in frontend, and join a group
        foo = User.objects.filter(email='foo@foo.com').first()
        if foo is None:
            foo = User.objects.create_user(
                email='foo@foo.com', password='foofoo', display_name='Playground User', is_staff=True
            )

        login_user(foo.id)
        join_group(groups[0]['id'])

        # Make sure we have a playground group
        if not Group.objects.filter(status=GroupStatus.PLAYGROUND.value).exists():
            group = Group.objects.order_by('?').first()
            group.status = GroupStatus.PLAYGROUND.value
            group.save()

        print_success('Done! You can login with any of those mail addresses and password {}'.format(default_password))
        if not options['more_data']:
            print_success('Consider using the --more argument next time for more users.')

        teardown_environment()
