from influxdb_metrics.loader import write_points

from foodsaving.groups.models import Group
from foodsaving.pickups.models import PickupDate


def pushed_via_websocket(topic):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'topic': topic,
        },
        'fields': {'websocket_push': 1},
    }])

