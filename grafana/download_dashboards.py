#!/bin/env python
"""
Downloads all Grafana dashboards from an organization for backup purposes, until we have generated dashboards

1. Go to https://grafana.karrot.world/org/apikeys (change to your hostname) and generate a new API key
2. Copy config.py.example to config.py and add your API key
3. Run "python download_dashboards.py"
4. Optional: Remove unused dashboards
5. Commit changes
"""

import json
import os
import shutil

import requests

import config

path = os.path.dirname(os.path.realpath(__file__))

try:
    shutil.rmtree(os.path.join(path, "dashboards"))
except FileNotFoundError:
    pass

os.mkdir(os.path.join(path, "dashboards"))

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {config.API_KEY}"})

dashboard_list = s.get(f"{config.GRAFANA_HOST}/api/search").json()
for dashboard in dashboard_list:
    type = dashboard["type"]
    if type != "dash-db":
        continue

    uid = dashboard["uid"]
    data = s.get(f"{config.GRAFANA_HOST}/api/dashboards/uid/{uid}").json()

    uri = dashboard["uri"].split("/")[-1]
    target_filepath = os.path.join(path, "dashboards", f"{uri}.json")

    with open(target_filepath, "w") as f:
        f.write(json.dumps(data, sort_keys=True, indent=2))
