from django.core.management import BaseCommand
from django_redis import get_redis_connection
from versatileimagefield.settings import VERSATILEIMAGEFIELD_SETTINGS


class Command(BaseCommand):
    def handle(self, *args, **options):
        print('Flushing sized image cache')
        # Ensures we use the same cache the versatileimagefield uses
        connection = get_redis_connection("default")
        sized_directory_name = VERSATILEIMAGEFIELD_SETTINGS['sized_directory_name']
        keys = connection.keys(f'*/{sized_directory_name}/*')
        for key in keys:
            connection.delete(key)
        print('Removed', len(keys))
