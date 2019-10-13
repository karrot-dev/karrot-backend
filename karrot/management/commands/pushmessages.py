import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        push_cmd = 'tx push -s'

        print(push_cmd)
        subprocess.run(push_cmd, shell=True, check=True)
