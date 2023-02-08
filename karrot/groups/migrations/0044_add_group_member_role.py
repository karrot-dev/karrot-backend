import django.contrib.postgres.fields
from django.db import migrations, models
import karrot.groups.models


def add_group_member_role(apps, schema_editor):
    GroupMembership = apps.get_model('groups', 'GroupMembership')

    for membership in GroupMembership.objects.all():
        if 'member' not in membership.roles:
            membership.roles.append('member')
            membership.save()


class Migration(migrations.Migration):

    dependencies = [
        ('groups', '0043_auto_20200717_1325'),
    ]

    operations = [
        migrations.RunPython(add_group_member_role, reverse_code=migrations.RunPython.noop, elidable=True),
    ]
