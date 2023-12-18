from unittest.mock import patch

from django.test import TestCase

from ..factories import InvitationFactory
from karrot.invitations.models import Invitation
from karrot.invitations.emails import prepare_emailinvitation_email


class PrepareEmailTestCase(TestCase):
    @patch("karrot.invitations.emails.prepare_email")
    def test_prepare_email_called_with_language(self, prepare_email):
        invitation: Invitation = InvitationFactory(invited_by__language="sw")

        prepare_emailinvitation_email(invitation)

        _, kwargs = prepare_email.call_args
        self.assertEqual(kwargs["language"], "sw")
