import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        extract_cmd = ' '.join([
            'pybabel extract',
            '-F babel.cfg',
            '-o foodsaving/locale/en/LC_MESSAGES/django.po',
            '.',
        ])
        print(extract_cmd)
        subprocess.run(extract_cmd, shell=True)
