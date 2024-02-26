from django.db.models import Count, Sum


class NonAggregatingCount(Count):
    """A COUNT that does not trigger a GROUP BY to be added

    This is useful when using Subquery in an annotation
    """

    contains_aggregate = False


class NonAggregatingSum(Sum):
    """A SUM that does not trigger a GROUP BY to be added

    This is useful when using Subquery in an annotation
    """

    contains_aggregate = False
