from karrot.utils.email_utils import prepare_email
from karrot.utils.frontend_urls import invite_url


def prepare_emailinvitation_email(invitation):
    return prepare_email(
        template="emailinvitation",
        user=None,
        tz=invitation.group.timezone,
        context={
            "group_name": invitation.group.name,
            "invite_url": invite_url(invitation),
            "email": invitation.email,
            "invited_by_name": invitation.invited_by.display_name,
            "group": invitation.group,
        },
        to=invitation.email,
        stats_category="invitation",
        language=invitation.invited_by.language,
    )
