from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model


class VerificationCodeManager:
    """
    A tool to generate and validate verification codes.

    A verification code is a single-use token that expires after a predefined period
    and can only be used by a designated user to authenticate for a certain action.
    """
    # Types of verification codes
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION'
    PASSWORD_RESET = 'PASSWORD_RESET'  # Will work as soon as we've added a password_valid attribute to the user model.
    ACCOUNT_DELETE = 'ACCOUNT_DELETE'
    TYPES = [EMAIL_VERIFICATION, PASSWORD_RESET, ACCOUNT_DELETE]

    # Debug modes
    DEBUG_VALIDITY_TIME_LIMIT = 'DEBUG_VALIDITY_TIME_LIMIT'
    DEBUG_MODES = [DEBUG_VALIDITY_TIME_LIMIT]

    _SALT = settings.VERIFICATION_CODE_SALT

    def __init__(self, type_, debug_mode=None):
        if type_ not in VerificationCodeManager.TYPES:
            raise NotImplementedError
        if debug_mode and debug_mode not in VerificationCodeManager.DEBUG_MODES:
            raise NotImplementedError

        self._type = type_
        self._debug_mode = debug_mode

    def generate_code(self, user):
        """
        Create a verification code for the given user.

        The code consists of the user's email address and the verification code type,
        base64 compressed and signed using Django's TimestampSigner.
        """
        assert (self._type == VerificationCodeManager.EMAIL_VERIFICATION and not user.mail_verified) \
            or (self._type == VerificationCodeManager.PASSWORD_RESET and not user.password_valid) \
            or self._type == VerificationCodeManager.ACCOUNT_DELETE

        return signing.dumps(
            obj=(user.email, self._type),
            salt=VerificationCodeManager._SALT
        )

    def _get_validity_time_limit(self):
        """
        Retrieve the validity time limit setting based on the verification code type.

        The validity time limit is the period of time after which the verification code expires.
        """
        if self._type == VerificationCodeManager.EMAIL_VERIFICATION:
            return settings.EMAIL_VERIFICATION_TIME_LIMIT_HOURS * 3600
        if self._type == VerificationCodeManager.PASSWORD_RESET:
            return settings.PASSWORD_RESET_TIME_LIMIT_MINUTES * 60
        if self._type == VerificationCodeManager.ACCOUNT_DELETE:
            return settings.ACCOUNT_DELETE_TIME_LIMIT_MINUTES * 60
        raise NotImplementedError

    def _validate_email_and_type(self, code):
        """
        Return the email address as plaintext if the verification code has not been tampered with.
        """
        validity_time_limit = 0 if self._debug_mode == VerificationCodeManager.DEBUG_VALIDITY_TIME_LIMIT \
            else self._get_validity_time_limit()

        try:
            email, actual_type = signing.loads(code, salt=VerificationCodeManager._SALT, max_age=validity_time_limit)
        except signing.BadSignature:
            return None

        return email if self._type == actual_type else None

    def _validate_user(self, email):
        """
        Return the user with the given email address if it exists and has not used the verification code yet.
        """
        User = get_user_model()

        try:
            if self._type == VerificationCodeManager.EMAIL_VERIFICATION:
                return User.objects.get(email=email, mail_verified=False)
            if self._type == VerificationCodeManager.PASSWORD_RESET:
                return User.objects.get(email=email, password_valid=False)
            if self._type == VerificationCodeManager.ACCOUNT_DELETE:
                return User.objects.get(email=email)
            raise NotImplementedError
        except User.DoesNotExist:
            return None

    def validate_code(self, code):
        """
        Return the authenticated user if the verification code is valid, else return None.
        """
        return self._validate_user(self._validate_email_and_type(code))
