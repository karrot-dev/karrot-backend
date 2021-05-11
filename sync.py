#!/usr/bin/env python

import subprocess
import os
import glob
import sys
from os.path import dirname, realpath, join
import pkgutil

process_mjml = '--no-mjml' not in sys.argv[1:]
install_hooks = '--no-hooks' not in sys.argv[1:]


def color(num):
    def format(val):
        return '\033[' + str(num) + 'm' + val + '\033[0m'

    return format


green = color(92)
yellow = color(93)
grey = color(90)


def header(val, greyed=False):
    if greyed:
        print('\n', grey('★'), grey(val))
    else:
        print('\n', yellow('★'), green(val), '\n')


environ = os.environ.copy()

# do not prompt if dependency source already exists, just wipe and get the required version
environ['PIP_EXISTS_ACTION'] = 'w'

base = dirname(realpath(__file__))

if 'piptools' not in [m.name for m in pkgutil.iter_modules()]:
    header("Installing pip-tools")
    subprocess.run(['pip', 'install', 'pip-tools'], env=environ, check=True)

header("Installing python dependencies")
subprocess.run(['pip-sync', 'requirements.txt'], env=environ, check=True)

if process_mjml:

    header("Installing node js dependencies")
    subprocess.run(['yarn'], env=environ, cwd=join(base, 'mjml'), check=True)

    header("Removing old templates")

    entries = glob.glob(join(base, 'karrot/*/templates/*.html.jinja2'))
    for entry in entries:
        os.remove(entry)
    print('Removed {} entries'.format(len(entries)))

    header("Generating new templates")
    subprocess.run(['./mjml/convert'], env=environ, check=True)
else:
    header("Skipped mjml processing", greyed=True)

if install_hooks:
    header("Installing pre-commit hooks")
    hook_types = ['pre-commit', 'pre-push']

    for t in hook_types:
        subprocess.run(['pre-commit', 'install', '--hook-type', t], env=environ, check=True)
else:
    header("Skipped hook installation", greyed=True)

header('All done ☺')
