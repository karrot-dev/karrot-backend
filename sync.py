#!/usr/bin/env python

import subprocess
import os
import glob
import sys
from os.path import dirname, realpath, join
import pkgutil

process_mjml = '--no-mjml' not in sys.argv[1:]


def color(num):
    def format(val):
        return '\033[' + str(num) + 'm' + val + '\033[0m'

    return format


green = color(92)
yellow = color(93)


def header(val):
    print('\n', yellow('★'), green(val), '\n')


def in_docker():
    return subprocess.run(['grep', 'docker', '/proc/1/cgroup'], stdout=subprocess.DEVNULL).returncode == 0


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

if in_docker():
    header("Not installing pre-commit hooks")
    print('This is because it appears I am running in a docker environment.')
    print('I am assuming you will be doing all your git stuff outside of the docker environment.')
    print('This means you should also setup the python environment outside of docker if you want to use the hooks.')
else:
    header("Installing pre-commit hooks")
    hook_types = ['pre-commit', 'pre-push']

    for t in hook_types:
        subprocess.run(['pre-commit', 'install', '--hook-type', t], env=environ, check=True)

header('All done ☺')
