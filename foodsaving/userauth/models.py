from django.db.models import CharField, DateTimeField

from foodsaving.base.base_models import BaseModel


class VerificationCode(BaseModel):
    EMAIL_VERIFICATION = 'EMAIL_VERIFICATION'
    EMAIL_CHANGE = 'EMAIL_CHANGE'
    PASSWORD_RESET = 'PASSWORD_RESET'
    ACCOUNT_DELETE = 'ACCOUNT_DELETE'

    TYPES = [EMAIL_VERIFICATION, EMAIL_CHANGE, PASSWORD_RESET, ACCOUNT_DELETE]

    verification_code = CharField(unique=True, max_length=50)
    type = CharField(max_length=50)
    used_at = DateTimeField(blank=True, null=True)