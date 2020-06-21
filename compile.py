#!/usr/bin/env python

import subprocess

subprocess.run(["pip-compile", "-U", "requirements.in"], check=True)
