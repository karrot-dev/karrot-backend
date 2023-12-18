from django.contrib.auth import get_user_model
from django.core.management import BaseCommand
from django.db.models import Q

from karrot.activities.models import Activity, create_activity_banner_image_warmer
from karrot.conversations.models import ConversationMessageImage, create_conversation_message_image_warmer
from karrot.groups.models import Group, create_group_photo_warmer
from karrot.offers.models import OfferImage, create_offer_image_warmer
from karrot.userauth.models import create_user_photo_warmer


class Command(BaseCommand):
    def handle(self, *args, **options):
        print("Warming user photos")
        succeeded, failed = create_user_photo_warmer(
            get_user_model().objects.filter(~Q(photo="") & ~Q(photo=None)),
            verbose=True,
        ).warm()
        print("succeeded", succeeded, "failed", len(failed))

        print("Warming group photos")
        succeeded, failed = create_group_photo_warmer(
            Group.objects.filter(~Q(photo="") & ~Q(photo=None)),
            verbose=True,
        ).warm()
        print("succeeded", succeeded, "failed", len(failed))

        print("Warming activity banner images")
        succeeded, failed = create_activity_banner_image_warmer(
            Activity.objects.filter(~Q(banner_image="") & ~Q(banner_image=None)),
            verbose=True,
        ).warm()
        print("succeeded", succeeded, "failed", len(failed))

        print("Warming offer images")
        succeeded, failed = create_offer_image_warmer(
            OfferImage.objects.all(),
            verbose=True,
        ).warm()
        print("succeeded", succeeded, "failed", len(failed))

        print("Warming conversation message images")
        succeeded, failed = create_conversation_message_image_warmer(
            ConversationMessageImage.objects.all(),
            verbose=True,
        ).warm()
        print("succeeded", succeeded, "failed", len(failed))
