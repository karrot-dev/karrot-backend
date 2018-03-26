"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, re_path, include
from django.views.static import serve
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework_nested import routers
from rest_framework_swagger.views import get_swagger_view

from foodsaving.conversations.api import ConversationMessageViewSet, ConversationViewSet
from foodsaving.groups.api import GroupViewSet, AgreementViewSet, GroupInfoViewSet
from foodsaving.history.api import HistoryViewSet
from foodsaving.invitations.api import InvitationsViewSet, InvitationAcceptViewSet
from foodsaving.pickups.api import PickupDateViewSet, PickupDateSeriesViewSet, FeedbackViewSet
from foodsaving.stores.api import StoreViewSet
from foodsaving.subscriptions.api import PushSubscriptionViewSet
from foodsaving.template_previews import views as template_preview_views
from foodsaving.userauth.api import AuthUserView, AuthView, LogoutView, \
    RequestResetPasswordView, ChangePasswordView, VerifyMailView, ResendMailVerificationCodeView, ResetPasswordView, \
    ChangeMailView, RequestDeleteUserView
from foodsaving.users.api import UserViewSet
from foodsaving.webhooks.api import IncomingEmailView, EmailEventView

router = routers.DefaultRouter()

router.register('groups', GroupViewSet)
router.register('groups-info', GroupInfoViewSet, base_name='groupinfo')
router.register('agreements', AgreementViewSet)

# User endpoints
router.register('users', UserViewSet)

# pickup date endpoints
router.register('pickup-date-series', PickupDateSeriesViewSet)
router.register('pickup-dates', PickupDateViewSet)

# Conversation/Message endpoints
router.register('conversations', ConversationViewSet)
router.register('messages', ConversationMessageViewSet)

# Subscription endpoints
router.register('subscriptions/push', PushSubscriptionViewSet)

# Store endpoints
router.register('stores', StoreViewSet)

# History endpoints
router.register('history', HistoryViewSet)

# Invitation endpoints
router.register('invitations', InvitationsViewSet)
router.register('invitations', InvitationAcceptViewSet)

# Feedback endpoints
router.register('feedback', FeedbackViewSet)

urlpatterns = [
    path('api/auth/token/', obtain_auth_token),
    path('api/auth/logout/', LogoutView.as_view()),
    path('api/auth/user/', AuthUserView.as_view()),
    path('api/auth/user/request_delete/', RequestDeleteUserView.as_view()),
    path('api/auth/email/', ChangeMailView.as_view()),
    path('api/auth/email/verify/', VerifyMailView.as_view()),
    path('api/auth/email/resend_verification_code/', ResendMailVerificationCodeView.as_view()),
    path('api/auth/password/', ChangePasswordView.as_view()),
    path('api/auth/password/request_reset/', RequestResetPasswordView.as_view()),
    path('api/auth/password/reset/', ResetPasswordView.as_view()),
    path('api/webhooks/incoming_email/', IncomingEmailView.as_view()),
    path('api/webhooks/email_event/', EmailEventView.as_view()),
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
