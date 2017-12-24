"""URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.0/topics/http/urls/
"""
from django.conf import settings
from django.contrib import admin
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import path, include, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from rest_framework.authtoken.views import obtain_auth_token
from rest_framework.documentation import include_docs_urls
from rest_framework_nested import routers

from foodsaving.conversations.api import ConversationMessageViewSet, ConversationViewSet
from foodsaving.groups.api import GroupViewSet, AgreementViewSet, GroupInfoViewSet
from foodsaving.history.api import HistoryViewSet
from foodsaving.invitations.api import InvitationsViewSet, InvitationAcceptViewSet
from foodsaving.pickups.api import PickupDateViewSet, PickupDateSeriesViewSet, FeedbackViewSet
from foodsaving.stores.api import StoreViewSet
from foodsaving.subscriptions.api import PushSubscriptionViewSet
from foodsaving.userauth.api import AuthUserView, AuthView, LogoutView, VerifyMailView, ResendVerificationView, \
    ResetPasswordView
from foodsaving.users.api import UserViewSet

router = routers.DefaultRouter()

router.register('groups', GroupViewSet)
router.register('groups-info', GroupInfoViewSet)
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

schema_view = get_schema_view(
    openapi.Info(
        title='Karrot API',
        default_version='v1',
        description='API documentation',
        contact=openapi.Contact(email='karrot@foodsaving.world'),
        license=openapi.License(name='AGPLv3'),
    ),
    public=False,
    permission_classes=(permissions.AllowAny,),
)

urlpatterns = [
    path('api/auth/token/', obtain_auth_token),
    path('api/auth/logout/', LogoutView.as_view()),
    path('api/auth/user/', AuthUserView.as_view()),
    path('api/auth/verify_mail/', VerifyMailView.as_view()),
    path('api/auth/resend_verification/', ResendVerificationView.as_view()),
    path('api/auth/reset_password/', ResetPasswordView.as_view()),
    path('api/auth/', AuthView.as_view()),
    path('api/', include(router.urls)),
    path('api-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('admin/docs/', include('django.contrib.admindocs.urls')),
    path('admin/', admin.site.urls),
    re_path(r'^drf_docs/', include_docs_urls(title='Karrot API', public=False)),
    re_path(r'^schema(?P<format>.json|.yaml)$', schema_view.without_ui(cache_timeout=None), name='schema-json'),
    re_path(r'^docs/$', schema_view.with_ui('swagger', cache_timeout=None), name='schema-swagger-ui'),
    re_path(r'^redoc/$', schema_view.with_ui('redoc', cache_timeout=None), name='schema-redoc'),
]

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
