#!/usr/bin/env python

import subprocess
import os
import glob
from os.path import dirname, realpath, join

environ = os.environ.copy()

# do not prompt if dependency source already exists, just wipe and get the required version
environ['PIP_EXISTS_ACTION'] = 'w'

base = dirname(realpath(__file__))

print("★ Installing python dependencies")
subprocess.run(['pip-sync', 'requirements.txt'], env=environ)

print("★ Installing node js dependencies")
subprocess.run(['yarn'], env=environ, cwd=join(base, 'mjml'))

print("★ Removing old templates")
for entry in glob.glob(join(base, 'foodsaving/*/templates/*.html.jinja2')):
    os.remove(entry)

print("★ Generating new templates")
subprocess.run(['./mjml/convert'], env=environ)
