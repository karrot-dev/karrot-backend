#!/usr/bin/env python

import subprocess
import os
import glob
import sys
from os.path import dirname, realpath, join

process_mjml = '--no-mjml' not in sys.argv[1:]


def color(num):
    def format(val):
        return '\033[' + str(num) + 'm' + val + '\033[0m'

    return format


green = color(92)
yellow = color(93)


def header(val):
    print('\n', yellow('★'), green(val), '\n')


environ = os.environ.copy()

# do not prompt if dependency source already exists, just wipe and get the required version
environ['PIP_EXISTS_ACTION'] = 'w'

base = dirname(realpath(__file__))

header("Installing python dependencies")
subprocess.run(['pip-sync', 'requirements.txt'], env=environ)

if process_mjml:

    header("Installing node js dependencies")
    subprocess.run(['yarn'], env=environ, cwd=join(base, 'mjml'))

    header("Removing old templates")

    entries = glob.glob(join(base, 'foodsaving/*/templates/*.html.jinja2'))
    for entry in entries:
        os.remove(entry)
    print('Removed {} entries'.format(len(entries)))

    header("Generating new templates")
    subprocess.run(['./mjml/convert'], env=environ)

header('All done ☺')
