from datetime import timedelta

import dateutil
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
        return abs(pickup.date - date)

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

        if (not diff_is_small or (next_pickup and get_diff(next_pickup, date) < diff)) and pickup.date < date:
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
    # using local time zone to avoid daylight saving time errors
    period_start_local = period_start.astimezone(tz).replace(tzinfo=None)
    dtstart_local = dtstart.astimezone(tz).replace(tzinfo=None)

    dates = dateutil.rrule.rrulestr(
        rule,
    ).replace(
        dtstart=dtstart_local,
    ).between(
        period_start_local,
        period_start_local + period_duration,
    )
    return [tz.localize(d) for d in dates]
