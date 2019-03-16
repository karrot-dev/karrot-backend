from influxdb_metrics.loader import write_points

from karrot.groups.stats import group_tags


def conversation_tags(conversation):
    type = conversation.type()
    group = conversation.group

    tags = group_tags(group) if group else {}

    if type is not None:
        tags['type'] = type
    else:
        tags['type'] = 'unknown'
    return tags


def message_written(message):
    write_points([{
        'measurement': 'karrot.events',
        'tags': {
            **conversation_tags(message.conversation),
            'is_reply': message.is_thread_reply(),
        },
        'fields': {
            'message': 1
        },
    }])


def reaction_given(reaction):
    write_points([{
        'measurement': 'karrot.events',
        'tags': conversation_tags(reaction.message.conversation),
        'fields': {
            'message_reaction': 1
        },
    }])
