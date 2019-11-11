from django.conf import settings

from karrot.conversations.models import Conversation
from karrot.utils.email_utils import formataddr, prepare_email
from karrot.utils.frontend_urls import new_offer_unsubscribe_url, offer_url
from karrot.webhooks.utils import make_local_part


def prepare_new_offer_notification_email(user, offer):
    conversation = Conversation.objects.get_for_target(offer)

    reply_to_name = offer.user.display_name

    local_part = make_local_part(conversation, user)
    reply_to = formataddr((reply_to_name, '{}@{}'.format(local_part, settings.SPARKPOST_RELAY_DOMAIN)))
    from_email = formataddr((offer.user.display_name, settings.DEFAULT_FROM_EMAIL))

    # TODO: wire up the unsubscribe logic whereever that happens
    unsubscribe_url = new_offer_unsubscribe_url(user, offer)

    first_image = offer.images.first()

    return prepare_email(
        template='new_offer',
        from_email=from_email,
        user=user,
        tz=offer.group.timezone,
        reply_to=[reply_to],
        unsubscribe_url=unsubscribe_url,
        context={
            'user_name': offer.user.display_name,
            'offer_photo': first_image.image.url if first_image else None,
            'offer_name': offer.name,
            'offer_description': offer.description,
            'group': offer.group,
            'conversation_url': offer_url(offer),
            'mute_url': unsubscribe_url,
            'new_offer_unsubscribe_url': unsubscribe_url,
        },
        stats_category='new_offer',
    )
