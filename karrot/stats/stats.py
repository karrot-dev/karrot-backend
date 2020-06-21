from influxdb_metrics.loader import write_points


def convert_stat(stat):
    tags = dict(stat)
    ms = tags.pop("ms")
    ms_resources = tags.pop("ms_resources")
    route_path = tags.pop("route_path")
    return {
        "measurement": "karrot.stats.frontend",
        "fields": {
            "ms": ms,
            "ms_resources": ms_resources,
            # Put route_path as field to avoid hitting max-values-per-tag limit in influxdb
            "route_path": route_path,
        },
        "tags": tags,
    }


def received_stats(stats):
    write_points([convert_stat(stat) for stat in stats])
