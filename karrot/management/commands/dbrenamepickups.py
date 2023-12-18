import re

from django.core.management import BaseCommand
from django.db import connection

#
# A script to migrate the database from "pickups" to "activities"
#
# We use the fancy postgres tables to find things like sequence names, etc...
#
# Without any args it will print out the queries it would run.
# Pass --execute to actually run it.
#


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", dest="execute")

    def handle(self, *args, **options):
        do_execute = options["execute"]

        def fetchall(query):
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
            return rows

        queries = [
            "truncate django_migrations",
            "update django_content_type set app_label = 'activities' where app_label = 'pickups'",
            "update django_content_type set model = 'activity' where model = 'pickupdate'",
            "update django_content_type set model = 'activityseries' where model = 'pickupdateseries'",
            "update django_content_type set model = 'activityparticipant' where model = 'pickupdatecollector'",
        ]

        def rename_notification_types(type_from, type_to):
            for (notification_type,) in fetchall(
                f"select type from notifications_notification where type like '%{type_from}%'"
            ):
                renamed = notification_type.replace(type_from, type_to)
                queries.append(
                    f"update notifications_notification set type = '{renamed}' where type = '{notification_type}'"
                )

        rename_notification_types("pickup", "activity")
        rename_notification_types("collector", "participant")

        def rename_jsonb_field(table, column, field_from, field_to):
            query = f"""
            update {table}
            set {column} = {column} - '{field_from}' || jsonb_build_object('{field_to}', {column}->'{field_from}')
            where {column} ? '{field_from}'
            """
            return re.sub("\\s+", " ", query).strip()

        # rename inside jsonb fields

        queries.append(rename_jsonb_field("notifications_notification", "context", "pickup_date", "activity"))
        queries.append(rename_jsonb_field("notifications_notification", "context", "pickup", "activity"))
        queries.append(
            rename_jsonb_field("notifications_notification", "context", "pickup_collector", "activity_participant")
        )
        queries.append(rename_jsonb_field("history_history", "payload", "pickup_date", "activity"))
        queries.append(rename_jsonb_field("history_history", "payload", "collectors", "participants"))
        queries.append(rename_jsonb_field("history_history", "payload", "max_collectors", "max_participants"))
        queries.append(rename_jsonb_field("history_history", "before", "pickup_date", "activity"))
        queries.append(rename_jsonb_field("history_history", "after", "pickup_date", "activity"))

        # foreign key columns

        def rename_columns(key_from, key_to):
            fkey_query = f"""
                select table_name, column_name from information_schema.columns where column_name = '{key_from}'
            """
            for table_name, _ in fetchall(fkey_query):
                return f"alter table {table_name} rename column {key_from} to {key_to}"

        queries.append(rename_columns("pickupdate_id", "activity_id"))
        queries.append(rename_columns("pickup_id", "activity_id"))
        queries.append(rename_columns("max_collectors", "max_participants"))

        # constraints

        def rename_constraints(constraint_from, constraint_to):
            constraints_query = f"""
                select table_name, constraint_name
                from information_schema.table_constraints
                where constraint_name like '%{constraint_from}%'
            """
            for table_name, constraint_name in fetchall(constraints_query):
                return "alter table {} rename constraint {} to {}".format(
                    table_name, constraint_name, constraint_name.replace(constraint_from, constraint_to)
                )

        rename_constraints("pickup", "activity")

        # indexes

        def rename_indexes(index_from, index_to):
            index_query = f"""
                select indexname from pg_indexes where schemaname = 'public' and indexname like '%{index_from}%'
            """
            for (indexname,) in fetchall(index_query):
                return f"alter index if exists {indexname} rename to {indexname.replace(index_from, index_to)}"

        queries.append(rename_indexes("pickup", "activity"))
        queries.append(rename_indexes("collector", "participant"))

        # sequences

        def rename_sequences(sequence_from, sequence_to):
            sequence_query = f"select relname from pg_class where relkind = 'S' and relname like '%{sequence_from}%'"
            for (relname,) in fetchall(sequence_query):
                return f"alter sequence if exists {relname} rename to {relname.replace(sequence_from, sequence_to)}"

        queries.append(rename_sequences("pickup", "activity"))
        queries.append(rename_sequences("collector", "participant"))

        # table renames, do it last so it doesn't invalidate queries that were created above with the old table names

        queries.append("alter table if exists pickups_pickupdate rename to activities_activity")
        queries.append("alter table if exists pickups_pickupdateseries rename to activities_activityseries")
        queries.append("alter table if exists pickups_pickupdate_collectors rename to activities_activity_participants")
        queries.append("alter table if exists pickups_feedback rename to activities_feedback")

        if do_execute:
            with connection.cursor() as cursor:
                for query in queries:
                    if query:
                        cursor.execute(query)
            print("done")
        else:
            for query in queries:
                if query:
                    print(query + ";")
