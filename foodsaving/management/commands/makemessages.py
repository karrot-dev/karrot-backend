import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        extract_cmd = 'pybabel extract -F babel.cfg -o foodsaving/locale/django.pot .'
        update_cmd = ' '.join([
            'pybabel update',
            '-D django',
            '-l en',
            '-i foodsaving/locale/django.pot',
            '-o foodsaving/locale/en/LC_MESSAGES/django.po',
        ])

        print(extract_cmd)
        subprocess.run(extract_cmd, shell=True)

        print()
        print()
        print(update_cmd)
        subprocess.run(update_cmd, shell=True)
