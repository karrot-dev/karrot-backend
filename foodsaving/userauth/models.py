from datetime import timedelta

from django.db.models import CharField, DateTimeField, ForeignKey
from django.db import models, transaction
from django.conf import settings
from django.utils import crypto, timezone

from foodsaving.base.base_models import BaseModel

# TODO:
# ~ Ensure each user can have at most one verification code of a certain type at a time.
# ~ 'Resend verification code' functionality


class VerificationCode(BaseModel):
    """
    A single-use token that expires after a predefined period
    and can only be used by a designated user to authenticate a certain type of action.
    """
    # Action types
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION'
    PASSWORD_RESET = 'PASSWORD_RESET'
    ACCOUNT_DELETE = 'ACCOUNT_DELETE'
    TYPES = [EMAIL_VERIFICATION, PASSWORD_RESET, ACCOUNT_DELETE]

    # Debug modes
    # DEBUG_VALIDITY_TIME_LIMIT = 'DEBUG_VALIDITY_TIME_LIMIT'
    # DEBUG_MODES = [DEBUG_VALIDITY_TIME_LIMIT]
    
    LENGTH = 20

    user = ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                      default=crypto.get_random_string(length=LENGTH))
    code = CharField('actual verification code', unique=True, max_length=50,
                     default=crypto.get_random_string(length=LENGTH))
    type = CharField(max_length=50)

    # For documentation and debugging purposes,
    # invalidate a verification code instead of deleting it right away.
    invalidated_at = DateTimeField(blank=True, null=True)

    def _get_validity_time_limit(self):
        """
        Retrieve the validity time limit setting in seconds based on the verification code type.

        The validity time limit is the period of time after which the verification code expires.
        """
        if self.type == self.EMAIL_VERIFICATION:
            return settings.EMAIL_VERIFICATION_TIME_LIMIT_HOURS * 3600
        if self.type == self.PASSWORD_RESET:
            return settings.PASSWORD_RESET_TIME_LIMIT_MINUTES * 60
        if self.type == self.ACCOUNT_DELETE:
            return settings.ACCOUNT_DELETE_TIME_LIMIT_MINUTES * 60
        raise NotImplementedError

    def _has_expired(self):
        return self.created_at + timedelta(seconds=self._get_validity_time_limit()) < timezone.now()

    def is_valid(self, code, user, type):
        """
        Check if the given verification code is of the given type and valid for the given user.
        """
        return code == self.code \
            and type == self.type \
            and user == self.user \
            and not self._has_expired() \
            and not self.invalidated_at

    @transaction.atomic
    def invalidate(self):
        self.invalidated_at = timezone.now()
        self.save()
