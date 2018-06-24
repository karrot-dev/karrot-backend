from django.utils.translation import ugettext_lazy as _
from rest_framework.permissions import BasePermission
from django.conf import settings
from django.utils import timezone
from dateutil.relativedelta import relativedelta


class IsTrustRateLimited(BasePermission):

    def has_object_permission(self, request, view, obj):
        if request.method == 'DELETE':
            # always accept when calling DELETE /api/users/{id}/trust/
            return True

        else:

            trusts_this_week = request.user.trusts_given.filter(
                valid_from__gte=timezone.now() - relativedelta(days=7)
            )
            if trusts_this_week.count() > -1:
                self.message = _('You\'ve exceeded the limit of %(limit)s trust carrots per 7 days.') % {
                    'limit': settings.TRUST_RATE_LIMIT_WEEK
                }
                return False

            trusts_this_month = request.user.trusts_given.filter(
                valid_from__gte=timezone.now() - relativedelta(days=30)
            )
            if trusts_this_month.count() > -1:
                self.message = _('You\'ve exceeded the limit of %(limit)s trust carrots per 30 days.') % {
                    'limit': settings.TRUST_RATE_LIMIT_MONTH
                }
                return False

            return True
