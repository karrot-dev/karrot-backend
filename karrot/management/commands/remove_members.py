from django.core.management import BaseCommand

from karrot.groups.models import Group
from karrot.history.models import History, HistoryTypus


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("emails", metavar="emails", type=str, nargs="+", help="email addresses")
        parser.add_argument("--group", help="group id", required=True)
        parser.add_argument("--message", help="message to go into history", required=True)

    def handle(self, *args, **options):
        emails = options["emails"]
        group_id = int(options["group"])
        message = options["message"]

        group = Group.objects.filter(id=group_id).first()

        if not group:
            print("Group not found")
            return

        print(f"{group.name} [{group.id}]")
        memberships = []
        missing = []
        for email in emails:
            membership = group.groupmembership_set.filter(user__email=email).first()
            if membership:
                print(f"  - {membership.user.display_name} [{membership.user.email}]")
                memberships.append(membership)
            else:
                missing.append(email)

        if len(missing) > 0:
            print("No membership info found for:")
            for email in missing:
                print(" -", email)
            return

        print(f'History message: "{message}"')

        result = input("Remove them? ")

        if result != "y":
            print("No action was taken")
            return

        users = []
        for membership in memberships:
            users.append(membership.user)
            membership.delete()
        History.objects.create(typus=HistoryTypus.MEMBER_REMOVED, group=group, users=users, message=message)

        print("Complete!")
