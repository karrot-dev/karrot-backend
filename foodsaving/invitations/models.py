import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.db.models import Q
from django.utils import timezone

import foodsaving.invitations.emails
from foodsaving.base.base_models import BaseModel


class InvitationQuerySet(models.QuerySet):
    @transaction.atomic
    def create_and_send(self, **kwargs):
        # TODO: make this into a periodic task
        self.delete_expired_invitations()

        invitation = self.create(**kwargs)
        invitation.send_mail()
        return invitation

    def all_expired(self):
        return self.filter(Q(expires_at__lt=timezone.now()))

    def delete_expired_invitations(self):
        self.all_expired().delete()


def get_default_expiry_date():
    return timezone.now() + timedelta(days=14)


class Invitation(BaseModel):
    objects = InvitationQuerySet.as_manager()

    class Meta:
        unique_together = ('email', 'group')

    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    email = models.EmailField()
    invited_by = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    group = models.ForeignKey('groups.Group', on_delete=models.CASCADE)
    expires_at = models.DateTimeField(default=get_default_expiry_date)

    def send_mail(self):
        foodsaving.invitations.emails.prepare_emailinvitation_email(self).send()

    def accept(self, user):
        # add user to group
        self.group.accept_invite(
            user=user,
            invited_by=self.invited_by,
            invited_at=self.created_at,
        )

        # select joined group as default
        user.current_group = self.group
        user.save()

        self.delete()

    def __str__(self):
        return "Invite to {0} by {1}".format(self.group.name, self.invited_by.display_name)
