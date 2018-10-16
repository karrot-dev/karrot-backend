#!/usr/bin/env python

import subprocess
import os
environ = os.environ.copy()

# do not prompt if dependency source already exists, just wipe and get the required version
environ['PIP_EXISTS_ACTION'] = 'w'

subprocess.run(['pip-sync', 'requirements.txt', 'requirements-dev.txt'], env=environ)
