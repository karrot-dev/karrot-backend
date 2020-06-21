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
        parser.add_argument("--execute", action="store_true", dest="execute")

    def handle(self, *args, **options):
        do_execute = options["execute"]

        def fetchall(query):
            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
            return rows

        queries = [
            "update django_content_type set app_label = 'places' where app_label = 'stores'",
            "update django_content_type set model = 'place' where model = 'store'",
            "update django_migrations set app = 'places' where app = 'stores'",
            "update django_migrations set name = replace(name, 'store', 'place')",
            "update notifications_notification set type = 'new_place' where type = 'new_store'",
        ]

        def rename_jsonb_field(table, column, field_from, field_to):
            query = """
            update {}
            set {} = {} - '{}' || jsonb_build_object('{}', {}->'{}')
            where {} ? '{}'
            """.format(
                table,
                column,
                column,
                field_from,
                field_to,
                column,
                field_from,
                column,
                field_from,
            )
            return re.sub("\\s+", " ", query).strip()

        # rename 'store' -> 'place' inside jsonb fields

        queries.append(
            rename_jsonb_field(
                "notifications_notification", "context", "store", "place"
            )
        )
        queries.append(
            rename_jsonb_field("history_history", "payload", "store", "place")
        )
        queries.append(
            rename_jsonb_field("history_history", "before", "store", "place")
        )
        queries.append(rename_jsonb_field("history_history", "after", "store", "place"))

        # foreign key columns

        fkey_query = "select table_name, column_name from information_schema.columns where column_name = 'store_id'"
        for table_name, column_name in fetchall(fkey_query):
            queries.append(
                "alter table {} rename column store_id to place_id".format(table_name)
            )

        # constraints

        for table_name, constraint_name in fetchall(
            """
                select table_name, constraint_name
                from information_schema.table_constraints
                where constraint_name like '%store%'
                """
        ):
            queries.append(
                "alter table {} rename constraint {} to {}".format(
                    table_name,
                    constraint_name,
                    constraint_name.replace("store", "place"),
                )
            )

        # indexes

        index_query = "select indexname from pg_indexes where schemaname = 'public' and indexname like '%store%'"
        for (indexname,) in fetchall(index_query):
            queries.append(
                "alter index if exists {} rename to {}".format(
                    indexname, indexname.replace("store", "place")
                )
            )

        # sequences

        sequence_query = "select relname from pg_class where relkind = 'S' and relname like '%store%'"
        for (relname,) in fetchall(sequence_query):
            queries.append(
                "alter sequence if exists {} rename to {}".format(
                    relname, relname.replace("store", "place")
                )
            )

        queries.append("alter table if exists stores_store rename to places_place")

        if do_execute:
            with connection.cursor() as cursor:
                for query in queries:
                    cursor.execute(query)
            print("done")
        else:
            for query in queries:
                print(query + ";")
