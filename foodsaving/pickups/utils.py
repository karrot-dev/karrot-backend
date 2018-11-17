import dateutil
from more_itertools import peekable


def match_pickups_with_dates(pickups, new_dates):
    """
    finds pickups and dates that are nearest and returns them as tuples
    every entry only gets returned once
    if there is no nearest pickup or date, returns None instead

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
        next_pickup = pickups.peek(None)
        next_date = new_dates.peek(None)

        if next_pickup and get_diff(next_pickup, date) < diff and pickup.date < date:
            yield pickup, None
            pickup = next(pickups, None)
        elif next_date and get_diff(pickup, next_date) < diff:
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
