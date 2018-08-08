from influxdb_metrics.loader import write_points

from foodsaving.groups.models import Group
from foodsaving.groups.stats import group_tags
from foodsaving.pickups.models import PickupDate


def conversation_tags(conversation):
    tags = {}
    target = conversation.target
    if isinstance(target, Group):
        tags = group_tags(target)
        tags['type'] = 'group'
    elif isinstance(target, PickupDate):
        tags = group_tags(target.store.group)
        tags['type'] = 'pickup'
    elif conversation.is_private:
        tags['type'] = 'private'
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
