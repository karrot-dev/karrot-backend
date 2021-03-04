import itertools

from karrot.utils.influxdb_utils import write_points


def pushed_via_websocket(topic):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'topic': topic,
        },
        'fields': {
            'websocket_push': 1
        },
    }])


def pushed_via_subscription(success_subscriptions, failure_subscriptions):
    # [('web', True), ('web', False), ('android', True), ...]
    platform_and_result = [(item.platform, True) for item in success_subscriptions] + \
        [(item.platform, False) for item in failure_subscriptions]

    def key(x):
        return x[0]

    measurements = []
    for platform, group in itertools.groupby(sorted(platform_and_result, key=key), key=key):
        group = list(group)
        measurements.append({
            'measurement': 'karrot.events',
            'tags': {
                'platform': platform,
            },
            'fields': {
                'subscription_push': sum(1 for _ in group if _[1] is True),
                'subscription_push_error': sum(1 for _ in group if _[1] is False)
            },
        })

    write_points(measurements)
