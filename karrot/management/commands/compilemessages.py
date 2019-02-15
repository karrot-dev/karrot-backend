import subprocess
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        compile_cmd = 'pybabel compile -D django -d karrot/locale -f'

        print(compile_cmd)
        subprocess.run(compile_cmd, shell=True)
