import itertools

from influxdb_metrics.loader import write_points


def pushed_via_websocket(topic):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'topic': topic,
        },
        'fields': {'websocket_push': 1},
    }])


def pushed_via_subscription(subscriptions):
    measurements = []
    for platform, group in itertools.groupby(sorted(item.platform for item in subscriptions)):
        measurements.append({
            'measurement': 'karrot.events',
            'tags': {
                'platform': platform,
            },
            'fields': {
                'subscription_push': sum(1 for _ in group)
            },
        })

    write_points(measurements)
