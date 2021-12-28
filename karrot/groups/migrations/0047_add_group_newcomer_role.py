import django.contrib.postgres.fields
from django.db import migrations, models
import karrot.groups.models


def add_group_newcomer_role(apps, schema_editor):
    GroupMembership = apps.get_model('groups', 'GroupMembership')

    for membership in GroupMembership.objects.all():
        if membership.roles == ['member']:
            membership.roles.append('newcomer')
            membership.save()


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0046_groupmembership_must_have_member_role'),
    ]

    operations = [
        migrations.RunPython(add_group_newcomer_role, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
