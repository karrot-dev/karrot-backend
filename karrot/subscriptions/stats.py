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


def pushed_via_web_push(success_count: int, error_count: int):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            'platform': 'web_push',
        },
        'fields': {
            'subscription_push': success_count,
            'subscription_push_error': error_count,
        },
    }])
