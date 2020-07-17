#!/usr/bin/env python

import subprocess
import sys

paths = sys.argv[1:]

if len(paths) == 0:
    paths.append('karrot')

args = [
    'yapf',
    '-i',
    '-r',
    '-e',
    'karrot/*/migrations',
    *paths,
]
print(' '.join(args))
subprocess.run(args)
