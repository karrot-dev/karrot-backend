from anymail.exceptions import AnymailAPIError
from django.contrib.auth import get_user_model
from huey.contrib.djhuey import db_task
from raven.contrib.django.raven_compat.models import client as sentry_client

from karrot.groups.models import GroupMembership, GroupNotificationType
from karrot.offers.emails import prepare_new_offer_notification_email


@db_task()
def notify_members_about_new_offer(offer):
    users = (
        offer.group.members.filter(
            groupmembership__in=GroupMembership.objects.active().with_notification_type(
                GroupNotificationType.NEW_OFFER
            ),
        )
        .exclude(id__in=get_user_model().objects.unverified(),)
        .exclude(id=offer.user.id)
    )

    for user in users:
        try:
            prepare_new_offer_notification_email(user, offer).send()
        except AnymailAPIError:
            sentry_client.captureException()
