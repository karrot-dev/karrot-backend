import re

from django.core.management import BaseCommand
from django.db import connection

#
# A script to migrate the database from "stores" to "places"
#
# We use the fancy postgres tables to find things like sequence names, etc...
#
# Without any args it will print out the queries it would run.
# Pass --execute to actually run it.
#


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('--execute', action='store_true', dest='execute')

    def handle(self, *args, **options):
        do_execute = options['execute']

        def fetchall(query):
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
            return rows

        queries = [
            "truncate django_migrations",
            "update django_content_type set app_label = 'activities' where app_label = 'pickups'",
            "update django_content_type set model = 'activity' where model = 'pickup'",
            "update notifications_notification set type = 'new_activity' where type = 'new_pickup'"
        ]

        def rename_jsonb_field(table, column, field_from, field_to):
            query = """
            update {}
            set {} = {} - '{}' || jsonb_build_object('{}', {}->'{}')
            where {} ? '{}'
            """.format(table, column, column, field_from, field_to, column, field_from, column, field_from)
            return re.sub('\\s+', ' ', query).strip()

        # rename 'store' -> 'place' inside jsonb fields

        queries.append(rename_jsonb_field('notifications_notification', 'context', 'pickup_date', 'activity_date'))
        queries.append(rename_jsonb_field('history_history', 'payload', 'pickup_date', 'activity_date'))
        queries.append(rename_jsonb_field('history_history', 'before', 'pickup_date', 'activity_date'))
        queries.append(rename_jsonb_field('history_history', 'after', 'pickup_date', 'activity_date'))

        # foreign key columns

        fkey_query = """
            select table_name, column_name from information_schema.columns where column_name = 'pickupdate_id'
        """
        for table_name, column_name in fetchall(fkey_query):
            queries.append("alter table {} rename column pickupdate_id to activitydate_id".format(table_name))

        fkey_query = """
            select table_name, column_name from information_schema.columns where column_name = 'pickup_id'
        """
        for table_name, column_name in fetchall(fkey_query):
            queries.append("alter table {} rename column pickup_id to activity_id".format(table_name))

        # constraints

        for table_name, constraint_name in fetchall("""
                select table_name, constraint_name
                from information_schema.table_constraints
                where constraint_name like '%pickup%'
                """):
            queries.append(
                "alter table {} rename constraint {} to {}".format(
                    table_name, constraint_name, constraint_name.replace('pickup', 'activity')
                )
            )

        # indexes

        index_query = "select indexname from pg_indexes where schemaname = 'public' and indexname like '%pickup%'"
        for indexname, in fetchall(index_query):
            queries.append(
                "alter index if exists {} rename to {}".format(indexname, indexname.replace('pickup', 'activity'))
            )

        # sequences

        sequence_query = "select relname from pg_class where relkind = 'S' and relname like '%pickup%'"
        for relname, in fetchall(sequence_query):
            queries.append(
                "alter sequence if exists {} rename to {}".format(relname, relname.replace('pickup', 'activity'))
            )

        queries.append("alter table if exists pickups_pickupdate rename to activities_activitydate")
        queries.append("alter table if exists pickups_pickupdateseries rename to activities_activitydateseries")
        queries.append(
            "alter table if exists pickups_pickupdate_collectors rename to activities_activitydate_collectors"
        )
        queries.append("alter table if exists pickups_feedback rename to activities_feedback")

        if do_execute:
            with connection.cursor() as cursor:
                for query in queries:
                    cursor.execute(query)
            print('done')
        else:
            for query in queries:
                print(query + ';')
