from django.contrib.auth import user_login_failed, user_logged_in
from django.db.models.signals import post_save
from django.dispatch import receiver

from karrot.userauth import stats
from karrot.users.models import User


@receiver(user_login_failed)
def failed_login(sender, credentials, **kwargs):
    stats.login_failed(email=credentials.get('email'))


@receiver(user_logged_in)
def user_logged_in_handler(sender, **kwargs):
    stats.login_successful()


@receiver(post_save, sender=User)
def user_post_save_handler(**kwargs):
    """Sends a metric to InfluxDB when a new User object is created."""
    if kwargs.get('created'):
        stats.user_created()
