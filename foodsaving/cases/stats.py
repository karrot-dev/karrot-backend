from influxdb_metrics.loader import write_points

from foodsaving.groups.stats import group_tags


def case_tags(case):
    tags = group_tags(case.group)
    tags.update({
        'type': case.type,
    })
    return tags


def case_created(case):
    write_points([{
        'measurement': 'karrot.events',
        'tags': case_tags(case),
        'fields': {
            'case_created': 1
        },
    }])


def voted(case):
    write_points([{
        'measurement': 'karrot.events',
        'tags': case_tags(case),
        'fields': {
            'case_vote': 1
        },
    }])


def vote_changed(case):
    write_points([{
        'measurement': 'karrot.events',
        'tags': case_tags(case),
        'fields': {
            'case_vote_changed': 1
        },
    }])


def vote_deleted(case):
    write_points([{
        'measurement': 'karrot.events',
        'tags': case_tags(case),
        'fields': {
            'case_vote_deleted': 1
        },
    }])


def get_case_stats(group):
    fields = {
        'count_total': group.cases.count(),
        'count_ongoing': group.cases.ongoing().count(),
        'count_decided': group.cases.decided().count(),
        'count_cancelled': group.cases.cancelled().count(),
    }

    return [{
        'measurement': 'karrot.group.cases',
        'tags': group_tags(group),
        'fields': fields,
    }]
