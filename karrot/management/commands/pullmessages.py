import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        pull_cmd = 'tx pull -a --force'

        print(pull_cmd)
        subprocess.run(pull_cmd, shell=True)
