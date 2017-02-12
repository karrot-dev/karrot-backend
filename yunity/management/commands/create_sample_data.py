from django.contrib.auth import get_user_model

from django.core.management.base import BaseCommand

from yunity.stores.factories import PickupDateSeries as PickupDateSeriesFactory


class Command(BaseCommand):

    def handle(self, *args, **options):
        user = get_user_model().objects.create_superuser('abc@example.com', 'abc')

        series = [PickupDateSeriesFactory() for _ in range(1000)]

        for _ in series:
            _.store.group.members.add(user)
