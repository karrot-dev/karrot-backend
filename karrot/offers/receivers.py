from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from karrot.conversations.models import Conversation
from karrot.offers.models import Offer, OfferImage
from karrot.offers.tasks import notify_members_about_new_offer
from karrot.utils.misc import on_transaction_commit


@receiver(post_save, sender=Offer)
@on_transaction_commit
def offer_saved(sender, instance, created, **kwargs):
    if created:
        offer = instance
        conversation = Conversation.objects.get_or_create_for_target(offer)
        conversation.join(offer.user)
        notify_members_about_new_offer(offer)


@receiver(post_delete, sender=OfferImage)
def delete_offer_image_files(sender, instance, **kwargs):
    instance.image.delete_all_created_images()
    instance.image.delete(save=False)
