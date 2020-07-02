from datetime import timedelta

from dateutil.rrule import rrulestr
from more_itertools import peekable


def match_activities_with_dates(activities, new_dates):
    """
    finds activities and dates that are match and returns them as tuples
    every entry only gets returned once
    if there is no matching activity or date, returns None instead

    both inputs need to be sorted by date, ascending
    """
    activities = peekable(activities)
    new_dates = peekable(new_dates)

    def get_diff(activity, date):
        return abs(activity.date.start - date)

    activity = next(activities, None)
    date = next(new_dates, None)

    while True:
        if not activity or not date:
            if not activity and not date:
                break
            yield activity, date
            activity = next(activities, None)
            date = next(new_dates, None)
            continue

        diff = get_diff(activity, date)
        diff_is_small = diff < timedelta(seconds=31)
        next_activity = activities.peek(None)
        next_date = new_dates.peek(None)
        is_past = activity.date.start < date

        if (not diff_is_small or (next_activity and get_diff(next_activity, date) < diff)) and is_past:
            # diff is too big or the next activity is closer to given date, so the current activity doesn't match a date
            yield activity, None
            activity = next(activities, None)
        elif not diff_is_small or (next_date and get_diff(activity, next_date) < diff):
            # diff is too big or the activity is closer to the next date, so the current date doesn't match an activity
            yield None, date
            date = next(new_dates, None)
        else:
            yield activity, date
            activity = next(activities, None)
            date = next(new_dates, None)


def rrule_between_dates_in_local_time(rule, dtstart, tz, period_start, period_duration):
    rule = rrulestr(rule)

    # using local time zone to avoid daylight saving time errors
    period_start_local = period_start.astimezone(tz).replace(tzinfo=None)
    dtstart_local = dtstart.astimezone(tz).replace(tzinfo=None)

    until = None
    # UNTIL needs to be in local time zone as well
    if rule._until is not None:
        until = rule._until.astimezone(tz).replace(tzinfo=None)

    rule = rule.replace(
        dtstart=dtstart_local,
        until=until,
    ).between(
        period_start_local,
        period_start_local + period_duration,
    )
    return [tz.localize(date) for date in rule]
