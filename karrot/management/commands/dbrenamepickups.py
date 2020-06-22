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
        ]

        def rename_notification_types(type_from, type_to):
            for notification_type, in fetchall(
                    f"select type from notifications_notification where type like '%{type_from}%'"):
                renamed = notification_type.replace(type_from, type_to)
                queries.append(
                    f"update notifications_notification set type = '{renamed}' where type = '{notification_type}'"
                )

        rename_notification_types('pickup', 'activity')
        rename_notification_types('collector', 'participant')

        def rename_jsonb_field(table, column, field_from, field_to):
            query = """
            update {}
            set {} = {} - '{}' || jsonb_build_object('{}', {}->'{}')
            where {} ? '{}'
            """.format(table, column, column, field_from, field_to, column, field_from, column, field_from)
            return re.sub('\\s+', ' ', query).strip()

        # rename 'store' -> 'place' inside jsonb fields

        queries.append(rename_jsonb_field('notifications_notification', 'context', 'pickup_date', 'activity'))
        queries.append(rename_jsonb_field('notifications_notification', 'context', 'pickup', 'activity'))
        queries.append(
            rename_jsonb_field('notifications_notification', 'context', 'pickup_collector', 'activity_participant')
        )
        queries.append(rename_jsonb_field('history_history', 'payload', 'pickup_date', 'activity'))
        queries.append(rename_jsonb_field('history_history', 'before', 'pickup_date', 'activity'))
        queries.append(rename_jsonb_field('history_history', 'after', 'pickup_date', 'activity'))

        # foreign key columns

        def rename_foreign_keys(key_from, key_to):
            fkey_query = f"""
                select table_name, column_name from information_schema.columns where column_name = '{key_from}'
            """
            for table_name, column_name in fetchall(fkey_query):
                return f"alter table {table_name} rename column {key_from} to {key_to}"

        queries.append(rename_foreign_keys('pickupdate_id', 'activity_id'))
        queries.append(rename_foreign_keys('pickup_id', 'activity_id'))

        # constraints

        def rename_constraints(constraint_from, constraint_to):
            for table_name, constraint_name in fetchall(f"""
                select table_name, constraint_name
                from information_schema.table_constraints
                where constraint_name like '%{constraint_from}%'
                """):
                return "alter table {} rename constraint {} to {}".format(
                    table_name, constraint_name, constraint_name.replace(constraint_from, constraint_to)
                )

        rename_constraints('pickup', 'activity')

        # indexes

        def rename_indexes(index_from, index_to):
            index_query = f"select indexname from pg_indexes where schemaname = 'public' and indexname like '%{index_from}%'"
            for indexname, in fetchall(index_query):
                return "alter index if exists {} rename to {}".format(
                    indexname, indexname.replace(index_from, index_to)
                )

        queries.append(rename_indexes('pickup', 'activity'))
        queries.append(rename_indexes('collector', 'participant'))

        # sequences

        def rename_sequences(sequence_from, sequence_to):
            sequence_query = f"select relname from pg_class where relkind = 'S' and relname like '%{sequence_from}%'"
            for relname, in fetchall(sequence_query):
                return "alter sequence if exists {} rename to {}".format(
                    relname, relname.replace(sequence_from, sequence_to)
                )

        queries.append(rename_sequences('pickup', 'activity'))
        queries.append(rename_sequences('collector', 'participant'))

        queries.append("alter table if exists pickups_pickupdate rename to activities_activitydate")
        queries.append("alter table if exists pickups_pickupdateseries rename to activities_activitydateseries")
        queries.append(
            "alter table if exists pickups_pickupdate_collectors rename to activities_activitydate_collectors"
        )
        queries.append("alter table if exists pickups_feedback rename to activities_feedback")

        if do_execute:
            with connection.cursor() as cursor:
                for query in queries:
                    if query:
                        cursor.execute(query)
            print('done')
        else:
            for query in queries:
                if query:
                    print(query + ';')
