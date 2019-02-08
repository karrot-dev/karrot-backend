import subprocess
from django.core.management.base import BaseCommand


def remove_creation_date():
    print('removing creation date...')
    with open('foodsaving/locale/en/LC_MESSAGES/django.po', 'r+') as f:
        lines = f.readlines()
        before = len(lines)

        f.seek(0)
        for line in lines:
            if line.startswith('"POT-Creation-Date'):
                continue
            f.write(line)
        f.truncate()

        f.seek(0)
        if len(f.readlines()) != before - 1:
            raise Exception('output not matched, something went wrong!')


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
        remove_creation_date()
