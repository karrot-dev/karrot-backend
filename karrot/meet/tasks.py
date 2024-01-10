from huey.contrib.djhuey import db_task

from karrot.activities.models import Activity
from karrot.groups.models import Group
from karrot.meet.meet_utils import parse_room_name
from karrot.meet.serializers import RoomSerializer
from karrot.places.models import Place
from karrot.subscriptions.models import ChannelSubscription
from karrot.subscriptions.utils import MockRequest, send_in_channel
from karrot.users.models import User


def get_subscriptions(room_name):
    subject_type, subject_ids = parse_room_name(room_name)
    if not subject_type:
        return
    if subject_type in ("group", "place", "activity"):
        group = None
        subject_id = subject_ids[0]
        if subject_type == "group":
            group = Group.objects.get(id=subject_id)
        elif subject_type == "place":
            place = Place.objects.get(id=subject_id)
            group = place.group
        elif subject_type == "activity":
            activity = Activity.objects.get(id=subject_id)
            group = activity.place.group
        if group:
            return ChannelSubscription.objects.recent().filter(user__groupmembership__group=group).distinct()
    elif subject_type == "user":
        users = User.objects.filter(id__in=subject_ids)
        return ChannelSubscription.objects.recent().filter(user__in=users).distinct()


@db_task()
def notify_room_changed(room):
    subscriptions = get_subscriptions(room.name)
    if subscriptions:
        for subscription in subscriptions:
            payload = RoomSerializer(room, context={"request": MockRequest(user=subscription.user)}).data
            send_in_channel(subscription.reply_channel, topic="meet:room", payload=payload)


@db_task()
def notify_room_ended(room_name):
    subscriptions = get_subscriptions(room_name)
    if subscriptions:
        for subscription in subscriptions:
            send_in_channel(subscription.reply_channel, topic="meet:room_ended", payload={"name": room_name})
