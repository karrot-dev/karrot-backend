# helpers to make using django shell easier
import sqlparse


def print_queryset_sql(qs):
    print(sqlparse.format(str(qs.query), reindent=True))


pqs = print_queryset_sql
