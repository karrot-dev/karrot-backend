from io import BytesIO
from os.path import join
from tarfile import TarFile, TarInfo
from tempfile import TemporaryDirectory, TemporaryFile
from typing import IO, List

import gnupg
import orjson
from django.apps import apps
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.contrib.contenttypes.models import ContentType
from pytz import BaseTzInfo

from karrot.activities.models import (
    Activity,
    ActivityParticipant,
    ActivitySeries,
    ActivityType,
    Feedback,
    FeedbackNoShow,
    ICSAuthToken,
    ParticipantType,
    SeriesParticipantType,
)
from karrot.agreements.models import Agreement
from karrot.applications.models import Application
from karrot.community_feed.models import CommunityFeedMeta
from karrot.conversations.models import (
    Conversation,
    ConversationMessage,
    ConversationMessageAttachment,
    ConversationMessageImage,
    ConversationMessageMention,
    ConversationMessageReaction,
    ConversationMeta,
    ConversationParticipant,
    ConversationThreadParticipant,
)
from karrot.groups.models import Group, GroupMembership, Role, Trust
from karrot.history.models import History
from karrot.invitations.models import Invitation
from karrot.issues.models import Issue, Option, Vote, Voting
from karrot.meet.models import Room, RoomParticipant
from karrot.migrate.serializers import (
    MigrateFileSerializer,
    get_migrate_serializer_class,
)
from karrot.notifications.models import Notification, NotificationMeta
from karrot.offers.models import Offer, OfferImage
from karrot.places.models import Place, PlaceStatus, PlaceSubscription, PlaceType
from karrot.subscriptions.models import ChannelSubscription, WebPushSubscription
from karrot.userauth.models import VerificationCode
from karrot.webhooks.models import EmailEvent, IncomingEmail

# This might seem a bit excessive to list each model we do *not* export
# ... but it's just precautionary to ensure it is really explicit which
# things get exported. If you add a model but don't export it, the tests
# will fail, and you can decide whether to mark that model excluded or
# whether to export it.
excluded_models = [
    Application,
    CommunityFeedMeta,
    Issue,
    Voting,
    Option,
    Vote,
    VerificationCode,
    ChannelSubscription,
    WebPushSubscription,
    Conversation,
    ConversationMeta,
    ConversationParticipant,
    ConversationMessage,
    ConversationMessageMention,
    ConversationThreadParticipant,
    ConversationMessageReaction,
    ConversationMessageImage,
    ConversationMessageAttachment,
    History,
    ICSAuthToken,
    Invitation,
    EmailEvent,
    IncomingEmail,
    Notification,
    NotificationMeta,
    Room,
    RoomParticipant,
]


class FakeRequest:
    user = AnonymousUser()

    def build_absolute_uri(self, *args, **kwargs):
        raise Exception(
            "build_absolute_uri got called which probably means you are trying to serialize a file "
            "field incorrectly, use the MigrateFileSerializer for that field"
        )


def serialize_value(value):
    if isinstance(value, BaseTzInfo):
        return str(value)
    raise TypeError


def export_to_file(group_ids: List[int], output_filename: str, password: str):
    with (
        TemporaryDirectory() as home,
        TemporaryFile() as tmp,
    ):
        # use a tmp home to ensure we have clean environment
        gpg = gnupg.GPG(gnupghome=home)
        export_to_io(group_ids, tmp)
        tmp.seek(0)

        result = gpg.encrypt_file(
            tmp,
            recipients=[],
            passphrase=password,
            symmetric="AES256",
            armor=False,
            output=output_filename,
        )

        if not result.ok:
            raise RuntimeError(result.status)


def export_to_io(group_ids: List[int], output: IO):
    with TarFile.open(fileobj=output, mode="w|xz") as tarfile:
        groups = Group.objects.filter(id__in=group_ids)
        if len(groups) != len(group_ids):
            print("Not all groups found")
            return

        fake_request = FakeRequest()
        serializer_context = {"request": fake_request}

        models = [
            model
            for model in apps.get_models()
            if model.__module__.startswith("karrot.") and model not in excluded_models
        ]

        def export_queryset(qs):
            MigrateSerializer = get_migrate_serializer_class(qs.model)
            if qs.model in excluded_models:
                raise ValueError(
                    f"model {qs.model.__name__} is marked as excluded "
                    f"if it should be exported you can remove it from the excluded_models list"
                )
            models.remove(qs.model)
            ct = ContentType.objects.get_for_model(qs.model)
            data_type = f"{ct.app_label}.{ct.model}"
            data = BytesIO()
            # uses .iterator() to not load all entries into memory
            for item in qs.order_by("pk").iterator():
                item_data = MigrateSerializer(item, context=serializer_context).data
                data.write(orjson.dumps(item_data, default=serialize_value))
                data.write(b"\n")
            data.seek(0)
            json_info = TarInfo(f"{data_type}.json")
            json_info.size = data.getbuffer().nbytes

            # before exporting the json export any files first
            # so when we import they are available
            for file in MigrateFileSerializer.exported_files:
                file_info = TarInfo(join("files", file.name))
                file_info.size = file.size
                tarfile.addfile(file_info, file)
            MigrateFileSerializer.exported_files = []

            tarfile.addfile(json_info, data)

        # the order of these exports is very important
        # anything that references something else must be below the thing it references

        # groups
        export_queryset(groups)

        # users
        export_queryset(get_user_model().objects.filter(groupmembership__group__in=groups))

        # membership / trust / roles
        export_queryset(Role.objects.filter(group__in=groups))
        export_queryset(GroupMembership.objects.filter(group__in=groups))
        export_queryset(Trust.objects.filter(membership__group__in=groups))

        # agreements
        export_queryset(Agreement.objects.filter(group__in=groups))

        # places
        export_queryset(PlaceType.objects.filter(group__in=groups))
        export_queryset(PlaceSubscription.objects.filter(place__group__in=groups))
        export_queryset(PlaceStatus.objects.filter(group__in=groups))
        export_queryset(Place.objects.filter(group__in=groups))

        # activities
        export_queryset(ActivityType.objects.filter(group__in=groups))
        export_queryset(ActivitySeries.objects.filter(place__group__in=groups))
        export_queryset(SeriesParticipantType.objects.filter(activity_series__place__group__in=groups))
        export_queryset(Activity.objects.filter(place__group__in=groups))
        export_queryset(ParticipantType.objects.filter(activity__place__group__in=groups))
        export_queryset(ActivityParticipant.objects.filter(activity__place__group__in=groups))

        # feedback
        export_queryset(Feedback.objects.filter(about__place__group__in=groups))
        export_queryset(FeedbackNoShow.objects.filter(feedback__about__place__group__in=groups))

        # offers
        export_queryset(Offer.objects.filter(group__in=groups))
        export_queryset(OfferImage.objects.filter(offer__group__in=groups))

        # if we have anything left, it's an error!
        if len(models) > 0:
            for model in models:
                print("not exported model", model.__module__, model.__name__)
            raise Exception(
                "not all models were exported "
                "if this is intentional then add the missing "
                "models to excluded_models"
            )
