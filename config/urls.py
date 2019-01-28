"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
"""
import os
from django.conf import settings
from django.conf.urls import url
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, re_path, include
from django.views.static import serve
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.routers import DefaultRouter

from foodsaving.applications.api import ApplicationViewSet
from foodsaving.issues.api import IssuesViewSet
from foodsaving.conversations.api import ConversationMessageViewSet, ConversationViewSet
from foodsaving.groups.api import GroupViewSet, AgreementViewSet, GroupInfoViewSet
from foodsaving.history.api import HistoryViewSet
from foodsaving.invitations.api import InvitationsViewSet, InvitationAcceptViewSet, InvitationResendEmailViewSet
from foodsaving.notifications.api import NotificationViewSet
from foodsaving.pickups.api import PickupDateViewSet, PickupDateSeriesViewSet, FeedbackViewSet
from foodsaving.stores.api import StoreViewSet
from foodsaving.subscriptions.api import PushSubscriptionViewSet
from foodsaving.template_previews import views as template_preview_views
from foodsaving.unsubscribe.api import UnsubscribeView
from foodsaving.userauth.api import AuthUserView, AuthView, LogoutView, \
    RequestResetPasswordView, ChangePasswordView, VerifyMailView, ResendMailVerificationCodeView, ResetPasswordView, \
    ChangeMailView, RequestDeleteUserView, FailedEmailDeliveryView
from foodsaving.users.api import UserViewSet, UserInfoViewSet
from foodsaving.webhooks.api import IncomingEmailView, EmailEventView
from rest_framework_swagger.views import get_swagger_view

router = DefaultRouter()

router.register('groups', GroupViewSet)
router.register('groups-info', GroupInfoViewSet, basename='groupinfo')
router.register('applications', ApplicationViewSet, basename='application')
router.register('agreements', AgreementViewSet)

router.register('issues', IssuesViewSet, basename='issues')

# User endpoints
router.register('users', UserViewSet)
router.register('users-info', UserInfoViewSet)

# pickup date endpoints
router.register('pickup-date-series', PickupDateSeriesViewSet)
router.register('pickup-dates', PickupDateViewSet)

# Conversation/Message endpoints
router.register('conversations', ConversationViewSet)
router.register('messages', ConversationMessageViewSet)

# Notification endpoints
router.register('notifications', NotificationViewSet)

# Subscription endpoints
router.register('subscriptions/push', PushSubscriptionViewSet)

# Store endpoints
router.register('stores', StoreViewSet)

# History endpoints
router.register('history', HistoryViewSet)

# Invitation endpoints
router.register('invitations', InvitationsViewSet)
router.register('invitations', InvitationAcceptViewSet)
router.register('invitations', InvitationResendEmailViewSet)

# Feedback endpoints
router.register('feedback', FeedbackViewSet)

urlpatterns = [
    path('api/auth/token/', obtain_auth_token),
    path('api/auth/logout/', LogoutView.as_view()),
    path('api/auth/user/', AuthUserView.as_view()),
    path('api/auth/user/request_delete/', RequestDeleteUserView.as_view()),
    path('api/auth/user/failed_email_deliveries/', FailedEmailDeliveryView.as_view()),
    path('api/auth/email/', ChangeMailView.as_view()),
    path('api/auth/email/verify/', VerifyMailView.as_view()),
    path('api/auth/email/resend_verification_code/', ResendMailVerificationCodeView.as_view()),
    path('api/auth/password/', ChangePasswordView.as_view()),
    path('api/auth/password/request_reset/', RequestResetPasswordView.as_view()),
    path('api/auth/password/reset/', ResetPasswordView.as_view()),
    path('api/webhooks/incoming_email/', IncomingEmailView.as_view()),
    path('api/webhooks/email_event/', EmailEventView.as_view()),
    path('api/unsubscribe/<token>/', UnsubscribeView.as_view()),
    path('api/auth/', AuthView.as_view()),
    path('api/', include((router.urls))),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('admin/docs/', include('django.contrib.admindocs.urls')),
    path('admin/', admin.site.urls),
    path('docs/', get_swagger_view()),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += [
        re_path(r'^media/(?P<path>.*)$', serve, {
            'document_root': settings.MEDIA_ROOT,
            'show_indexes': True,
        }),
    ]
    urlpatterns += [
        path('_templates', template_preview_views.list_templates),
        path('_templates/show', template_preview_views.show_template),
    ]

if 'USE_SILK' in os.environ:
    urlpatterns += [url(r'^silk/', include('silk.urls', namespace='silk'))]
