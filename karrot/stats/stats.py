from influxdb_metrics.loader import write_points


def convert_stat(stat):
    ms = stat.pop('ms')
    return {
        'measurement': 'karrot.stats.frontend',
        'fields': {
            'ms': ms,
        },
        'tags': stat,
    }


def received_stats(stats):
    write_points([convert_stat(stat) for stat in stats])
