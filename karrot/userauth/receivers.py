from django.contrib.auth import user_login_failed
from django.dispatch import receiver

from karrot.userauth import stats


@receiver(user_login_failed)
def failed_login(sender, credentials, **kwargs):
    stats.login_failed(email=credentials.get('email'))
