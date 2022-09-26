#!/usr/bin/env python

import subprocess

subprocess.run(['pip-compile', '--no-annotate', '-U', 'requirements.in'], check=True)
