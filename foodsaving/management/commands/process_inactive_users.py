
from django.core.management.base import BaseCommand

from datetime import timedelta, datetime
from django.utils import timezone
from foodsaving.groups.models import GroupMembership
from config import settings
from foodsaving.utils.email_utils import prepare_user_inactive_in_group_email, prepare_user_removed_from_group_email


class Command(BaseCommand):

    def send_inactive_in_group_notification_to_user(self, user, group):
        print('Sending email to userid=', user.id, 'regarding inactivity in groupid=', group.id)
        email = prepare_user_inactive_in_group_email(user, group)
        email.send()

    def send_removal_from_group_notification_to_user(self, user, group):
        print('Sending email to userid=', user.id, 'regarding removal from groupid=', group.id)
        email = prepare_user_removed_from_group_email(user, group)
        email.send()

    def handle(self, *args, **options):
        now = timezone.now()

        print("Processing inactive users")

        remove_threshold_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_REMOVED_FROM_GROUP)
        print("Removing inactive users in groups who have been inactive since:",
              datetime.strftime(remove_threshold_date, '%Y-%m-%d'))
        for gm in GroupMembership.objects.all().filter(lastseen_at__lte=remove_threshold_date, isactive=False):
            self.send_removal_from_group_notification_to_user(gm.user, gm.group)
            gm.delete()

        inactive_threshold_date = now - timedelta(days=settings.NUMBER_OF_DAYS_UNTIL_INACTIVE_IN_GROUP)
        print("Flagging inactive users in groups who have been inactive since:",
              datetime.strftime(inactive_threshold_date, '%Y-%m-%d'))
        for gm in GroupMembership.objects.all().filter(lastseen_at__lte=inactive_threshold_date, isactive=True):
            self.send_inactive_in_group_notification_to_user(gm.user, gm.group)
            gm.isactive = False
            gm.save()






