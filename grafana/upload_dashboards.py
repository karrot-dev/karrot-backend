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
import sys

import requests

import config

path = os.path.dirname(os.path.realpath(__file__))

dashboard_dir = os.path.join(path, "dashboards")

s = requests.Session()
s.headers.update({"Authorization": f"Bearer {config.API_KEY}"})


def ask(question):
    sys.stdout.write(question)
    answer = input().lower()
    return answer == "y"


for entry in os.listdir(dashboard_dir):
    with open(os.path.join(dashboard_dir, entry)) as f:
        data = json.loads(f.read())
        # see https://grafana.com/docs/grafana/latest/http_api/dashboard/#create-update-dashboard
        update_data = {
            "dashboard": data["dashboard"],
            "folderId": data["meta"]["folderId"],
            "overwrite": False,
        }
        dashboard_url = "{host}/d/{uid}".format(host=config.GRAFANA_HOST, uid=data["dashboard"]["uid"])
        if ask(f"Update dashboard {entry} ({dashboard_url})? [y/N] "):
            res = s.post(f"{config.GRAFANA_HOST}/api/dashboards/db", json=data)
            print(res)
            print(res.json())
