import subprocess
import sys
from pathlib import Path

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    def handle(self, *args, **options):
        bin = Path(sys.exec_prefix) / "bin" / "pybabel"

        compile_cmd = f"{bin} compile -D django -d karrot/locale -f"

        print(compile_cmd)
        subprocess.run(compile_cmd, shell=True, check=True)
