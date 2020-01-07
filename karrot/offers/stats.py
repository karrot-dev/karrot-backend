from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def offer_tags(offer):
    return group_tags(offer.group)


def offer_created(offer):
    write_points([{
        'measurement': 'karrot.events',
        'tags': offer_tags(offer),
        'fields': {
            'offer_created': 1
        },
    }])


def offer_archived(offer):
    write_points([{
        'measurement': 'karrot.events',
        'tags': offer_tags(offer),
        'fields': {
            'offer_archived': 1
        },
    }])
