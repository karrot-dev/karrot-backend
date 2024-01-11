from huey.contrib.djhuey import db_task

from karrot.meet.meet_utils import get_room_group, parse_room_subject
from karrot.subscriptions.models import ChannelSubscription
from karrot.subscriptions.utils import send_in_channel
from karrot.users.models import User


def get_subscriptions(room_subject):
    subject_type, subject_ids = parse_room_subject(room_subject)
    if not subject_type:
        return ChannelSubscription.objects.none()
    if subject_type in ("group", "place", "activity"):
        group = get_room_group(room_subject)
        if group:
            return ChannelSubscription.objects.recent().filter(user__groupmembership__group=group).distinct()
    elif subject_type == "user":
        users = User.objects.filter(id__in=subject_ids)
        return ChannelSubscription.objects.recent().filter(user__in=users).distinct()


@db_task()
def notify_room_changed(payload):
    subscriptions = get_subscriptions(payload["subject"])
    if subscriptions:
        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic="meet:room", payload=payload)


@db_task()
def notify_room_ended(payload):
    """Accepts the payload, as we will have deleted the actual Room object"""
    subscriptions = get_subscriptions(payload["subject"])
    if subscriptions:
        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic="meet:room_ended", payload=payload)
