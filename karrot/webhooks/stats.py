from influxdb_metrics.loader import write_points


def incoming_email_rejected():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'incoming_email_rejected': 1,
        },
    }])


def incoming_email_trimmed(fields):
    write_points([{
        'measurement': 'karrot.incoming_email',
        'fields': fields,
    }])
