#!/bin/env python
"""
Downloads all Grafana dashboards from an organization for backup purposes, until we have generated dashboards

1. Go to https://grafana.karrot.world/org/apikeys (change to your hostname) and generate a new API key
2. Copy config.py.example to config.py and add your API key
3. Run "python download_dashboards.py"
4. Optional: Remove unused dashboards
5. Commit changes
"""

import requests
import os
import shutil
import sys
import json

import config

path = os.path.dirname(os.path.realpath(__file__))

dashboard_dir = os.path.join(path, 'dashboards')

s = requests.Session()
s.headers.update({'Authorization': 'Bearer {}'.format(config.API_KEY)})

def ask(question):
    sys.stdout.write(question)
    answer = input().lower()
    return answer == 'y'

for entry in os.listdir(dashboard_dir):
  with open(os.path.join(dashboard_dir, entry)) as f:
    data = json.loads(f.read())
    # see https://grafana.com/docs/grafana/latest/http_api/dashboard/#create-update-dashboard
    update_data = {
      'dashboard': data['dashboard'],
      'folderId': data['meta']['folderId'],
      'overwrite': False,  # Set to true if you want to overwrite existing dashboard with newer version, same dashboard title in folder or same dashboard uid.
    }
    #update_data['dashboard']['version'] += 1
    dashboard_url = '{host}/d/{uid}'.format(host=config.GRAFANA_HOST, uid=data['dashboard']['uid'])
    if ask('Update dashboard {} ({})? [y/N] '.format(entry, dashboard_url)):
      res = s.post('{host}/api/dashboards/db'.format(host=config.GRAFANA_HOST), json=data)
      print(res)
      print(res.json())

if False:

  dashboard_list = s.get('{host}/api/search'.format(host=config.GRAFANA_HOST)).json()
  for dashboard in dashboard_list:
      type = dashboard['type']
      if type != 'dash-db':
          continue

      uid = dashboard['uid']
      data = s.get('{host}/api/dashboards/uid/{uid}'.format(host=config.GRAFANA_HOST, uid=uid)).json()

      uri = dashboard['uri'].split('/')[-1]
      target_filepath = os.path.join(path, 'dashboards', '{}.json'.format(uri))

      with open(target_filepath, 'w') as f:
          f.write(json.dumps(data, sort_keys=True, indent=2))
