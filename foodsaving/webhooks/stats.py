from influxdb_metrics.loader import write_points


def incoming_email_rejected():
    write_points([{
        'measurement': 'karrot.events',
        'fields': {
            'incoming_email_rejected': 1,
        },
    }])
