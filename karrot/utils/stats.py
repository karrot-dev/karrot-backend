from karrot.utils.influxdb_utils import write_points


def email_sent(recipient_count, category):
    write_points([{
        'measurement': 'karrot.email.sent',
        'tags': {
            'category': category,
        },
        'fields': {
            'value': 1,
            'recipient_count': recipient_count
        },
    }])


def email_retry(recipient_count, category):
    write_points([{
        'measurement': 'karrot.email.retry',
        'tags': {
            'category': category,
        },
        'fields': {
            'value': 1,
            'recipient_count': recipient_count
        },
    }])


def email_error(recipient_count, category):
    write_points([{
        'measurement': 'karrot.email.error',
        'tags': {
            'category': category,
        },
        'fields': {
            'value': 1,
            'recipient_count': recipient_count
        },
    }])
