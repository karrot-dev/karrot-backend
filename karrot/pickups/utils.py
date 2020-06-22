from datetime import timedelta

from dateutil.rrule import rrulestr
from more_itertools import peekable


def match_pickups_with_dates(pickups, new_dates):
    """
    finds pickups and dates that are match and returns them as tuples
    every entry only gets returned once
    if there is no matching pickup or date, returns None instead

    both inputs need to be sorted by date, ascending
    """
    pickups = peekable(pickups)
    new_dates = peekable(new_dates)

    def get_diff(pickup, date):
        return abs(pickup.date.start - date)

    pickup = next(pickups, None)
    date = next(new_dates, None)

    while True:
        if not pickup or not date:
            if not pickup and not date:
                break
            yield pickup, date
            pickup = next(pickups, None)
            date = next(new_dates, None)
            continue

        diff = get_diff(pickup, date)
        diff_is_small = diff < timedelta(seconds=31)
        next_pickup = pickups.peek(None)
        next_date = new_dates.peek(None)
        is_past = pickup.date.start < date

        if (not diff_is_small or (next_pickup and get_diff(next_pickup, date) < diff)) and is_past:
            # diff is too big or the next pickup is closer to given date, so the current pickup doesn't match a date
            yield pickup, None
            pickup = next(pickups, None)
        elif not diff_is_small or (next_date and get_diff(pickup, next_date) < diff):
            # diff is too big or the pickup is closer to the next date, so the current date doesn't match a pickup
            yield None, date
            date = next(new_dates, None)
        else:
            yield pickup, date
            pickup = next(pickups, None)
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
