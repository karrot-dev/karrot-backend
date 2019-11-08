from django.db.models.signals import post_save
from django.dispatch import receiver

from karrot.conversations.models import Conversation
from karrot.offers.models import Offer
from karrot.offers.tasks import notify_members_about_new_offer


@receiver(post_save, sender=Offer)
def offer_saved(sender, instance, created, **kwargs):
    if created:
        offer = instance
        conversation = Conversation.objects.get_or_create_for_target(offer)
        conversation.join(offer.user)

        notify_members_about_new_offer(offer)
