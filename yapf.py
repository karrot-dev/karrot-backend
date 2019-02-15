#!/usr/bin/env python

import subprocess
import sys
args = [
    'yapf',
    '-i',
    '-r',
    '-e',
    'karrot/*/migrations',
    'karrot',
    *sys.argv[1:],
]
print(' '.join(args))
subprocess.run(args)
