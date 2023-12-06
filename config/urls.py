"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
"""

from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path, re_path
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from karrot.activities.api import (
    ActivitySeriesViewSet,
    ActivityTypeViewSet,
    ActivityViewSet,
    FeedbackViewSet,
    PublicActivityViewSet,
)
from karrot.agreements.api import AgreementViewSet
from karrot.applications.api import ApplicationViewSet
from karrot.bootstrap.api import BootstrapViewSet, ConfigViewSet
from karrot.community_feed.api import CommunityFeedViewSet
from karrot.conversations.api import AttachmentViewSet, ConversationMessageViewSet, ConversationViewSet
from karrot.groups.api import GroupInfoViewSet, GroupViewSet
from karrot.history.api import HistoryViewSet
from karrot.invitations.api import InvitationAcceptViewSet, InvitationsViewSet
from karrot.issues.api import IssuesViewSet
from karrot.meet.api import MeetRoomViewSet, MeetTokenViewSet, MeetWebhookViewSet
from karrot.notifications.api import NotificationViewSet
from karrot.offers.api import OfferViewSet
from karrot.places.api import PlaceStatusViewSet, PlaceTypeViewSet, PlaceViewSet
from karrot.plugins.api import PluginViewSet
from karrot.stats.api import ActivityHistoryStatsViewSet, FrontendStatsView
from karrot.status.api import StatusView
from karrot.subscriptions.api import WebPushSubscriptionViewSet
from karrot.template_previews import views as template_preview_views
from karrot.unsubscribe.api import TokenUnsubscribeView, UnsubscribeViewSet
from karrot.userauth.api import (
    AuthUserView,
    AuthView,
    ChangeMailView,
    ChangePasswordView,
    FailedEmailDeliveryView,
    LogoutView,
    RequestDeleteUserView,
    RequestResetPasswordView,
    ResendMailVerificationCodeView,
    ResetPasswordView,
    VerifyMailView,
)
from karrot.users.api import UserInfoViewSet, UserViewSet

router = DefaultRouter()

router.register("config", ConfigViewSet, basename="config")
router.register("bootstrap", BootstrapViewSet, basename="bootstrap")

router.register("groups", GroupViewSet)
router.register("groups-info", GroupInfoViewSet, basename="groupinfo")
router.register("applications", ApplicationViewSet, basename="application")
router.register("community-feed", CommunityFeedViewSet, basename="community-feed")
router.register("issues", IssuesViewSet, basename="issues")

router.register("agreements", AgreementViewSet)

# User endpoints
router.register("users", UserViewSet)
router.register("users-info", UserInfoViewSet, basename="userinfo")

# activity endpoints
router.register("activity-series", ActivitySeriesViewSet)
router.register("activities", ActivityViewSet)
router.register("activity-types", ActivityTypeViewSet)
router.register("public-activities", PublicActivityViewSet, basename="publicactivities")

# Conversation/Message endpoints
router.register("conversations", ConversationViewSet)
router.register("messages", ConversationMessageViewSet)
router.register("attachments", AttachmentViewSet)

# Notification endpoints
router.register("notifications", NotificationViewSet)

# Subscription endpoints
router.register("subscriptions/web-push", WebPushSubscriptionViewSet)

# Offer endpoints
router.register("offers", OfferViewSet)

# Place endpoints
router.register("places", PlaceViewSet)
router.register("place-types", PlaceTypeViewSet)
router.register("place-statuses", PlaceStatusViewSet)

# History endpoints
router.register("history", HistoryViewSet)

# Invitation endpoints
router.register("invitations", InvitationsViewSet)
router.register("invitations", InvitationAcceptViewSet, basename="invitationsaccept")

# Feedback endpoints
router.register("feedback", FeedbackViewSet)

router.register("unsubscribe", UnsubscribeViewSet, basename="unsubscribe")

# Meet rooms
router.register("meet/rooms", MeetRoomViewSet)

# Stats endpoints
router.register("stats/activity-history", ActivityHistoryStatsViewSet, basename="statsactivityhistory")

# Plugins
router.register("plugins", PluginViewSet, basename="plugins")

urlpatterns = [
    path("api/auth/token/", obtain_auth_token),
    path("api/auth/logout/", LogoutView.as_view()),
    path("api/auth/user/", AuthUserView.as_view()),
    path("api/auth/user/request_delete/", RequestDeleteUserView.as_view()),
    path("api/auth/user/failed_email_deliveries/", FailedEmailDeliveryView.as_view()),
    path("api/auth/email/", ChangeMailView.as_view()),
    path("api/auth/email/verify/", VerifyMailView.as_view()),
    path("api/auth/email/resend_verification_code/", ResendMailVerificationCodeView.as_view()),
    path("api/auth/password/", ChangePasswordView.as_view()),
    path("api/auth/password/request_reset/", RequestResetPasswordView.as_view()),
    path("api/auth/password/reset/", ResetPasswordView.as_view()),
    path("api/unsubscribe/<str:token>/", TokenUnsubscribeView.as_view()),
    path("api/auth/", AuthView.as_view()),
    path("api/stats/", FrontendStatsView.as_view()),
    path("api/status/", StatusView.as_view()),
    path("api/meet/token/", MeetTokenViewSet.as_view()),
    path("api/meet/webhook/", MeetWebhookViewSet.as_view()),
    path("api/", include(router.urls)),
    path("api-auth/", include("rest_framework.urls", namespace="rest_framework")),
    path("admin/docs/", include("django.contrib.admindocs.urls")),
    path("admin/", admin.site.urls),
    path("docs/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/anymail/", include("anymail.urls")),
    path("silk/", include("silk.urls", namespace="silk")),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += [
        re_path(
            r"^media/(?P<path>.*)$",
            serve,
            {
                "document_root": settings.MEDIA_ROOT,
                "show_indexes": True,
            },
        ),
    ]
    urlpatterns += [
        path("_templates", template_preview_views.list_templates),
        path("_templates/show", template_preview_views.show_template),
    ]
