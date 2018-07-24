from django.db.models.signals import post_save
from django.dispatch import receiver

from foodsaving.groups import roles
from foodsaving.groups.models import GroupMembership
from foodsaving.trust.models import Trust


@receiver(post_save, sender=Trust)
def maybe_make_editor(sender, instance, created, **kwargs):
    if not created:
        return
    user = instance.user
    group = instance.group
    relevant_trust = Trust.objects.filter(
        group=group,
        user=user,
        given_by__groupmembership__roles__contains=[roles.GROUP_EDITOR],
    )

    if relevant_trust.count() >= 3:
        membership = GroupMembership.objects.get(user=user, group=group)
        membership.add_roles([roles.GROUP_EDITOR])
        membership.save()

