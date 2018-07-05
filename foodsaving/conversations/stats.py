from influxdb_metrics.loader import write_points

from foodsaving.groups.models import Group
from foodsaving.pickups.models import PickupDate


def message_written(message):
    write_points([{
        'measurement': 'karrot.events',
        'tags': tags_for_conversation(message.conversation),
        'fields': {'message': 1},
    }])


def reaction_given(reaction):
    write_points([{
        'measurement': 'karrot.events',
        'tags': tags_for_conversation(reaction.message.conversation),
        'fields': {'message_reaction': 1},
    }])


def tags_for_conversation(conversation):
    tags = {}
    target = conversation.target
    if isinstance(target, Group):
        tags['group'] = target.id
        tags['type'] = 'group'
    elif isinstance(target, PickupDate):
        tags['group'] = target.store.group_id
        tags['type'] = 'pickup'
    elif conversation.is_private:
        tags['type'] = 'private'
    else:
        tags['type'] = 'unknown'
    return tags
