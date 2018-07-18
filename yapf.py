#!/usr/bin/env python

import subprocess
subprocess.run([
    'yapf',
    '-i',
    '-r',
    '-e',
    'foodsaving/*/migrations',
    'foodsaving',
])
