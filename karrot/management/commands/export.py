from argparse import FileType
from sys import stdout

import orjson
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.management import BaseCommand

from karrot.activities.models import Activity, Feedback
from karrot.activities.serializers import ActivitySerializer, FeedbackSerializer
from karrot.groups.models import Group
from karrot.groups.serializers import GroupPreviewSerializer
from karrot.places.models import Place
from karrot.places.serializers import PlaceSerializer
from karrot.users.serializers import UserSerializer


class FakeRequest:
    user = AnonymousUser()


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--groups', help='group ids', required=True)
        # TODO: make sure this closes properly
        parser.add_argument('output', nargs='?', type=FileType('wb'), default=stdout.buffer)

    def handle(self, *args, **options):
        output = options['output']
        group_ids = [int(group_id) for group_id in options['groups'].split(',')]
        groups = Group.objects.filter(id__in=group_ids)
        if len(groups) != len(group_ids):
            print('Not all groups found')
            return

        fake_request = FakeRequest()
        serializer_context = {'request': fake_request}

        def export_queryset(data_type, qs, serializer_class):
            for item in qs.iterator():
                entry = {
                    "type": data_type,
                    "data": serializer_class(item, context=serializer_context).data,
                }
                output.write(orjson.dumps(entry))
                output.write(b'\n')

        # groups
        export_queryset(
            "group",
            groups,
            GroupPreviewSerializer,
        )

        # users
        export_queryset(
            "user",
            get_user_model().objects.filter(groupmembership__group__in=groups),
            UserSerializer,
        )

        # places
        export_queryset(
            "place",
            Place.objects.filter(group__in=groups),
            PlaceSerializer,
        )

        # activities
        export_queryset(
            "activity",
            Activity.objects.filter(place__group__in=groups),
            ActivitySerializer,
        )

        # feedback
        export_queryset(
            "feedback",
            Feedback.objects.filter(about__place__group__in=groups),
            FeedbackSerializer,
        )
