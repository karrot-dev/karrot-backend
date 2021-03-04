from timeit import default_timer

from karrot.utils.influxdb_utils import write_points


def periodic_task(name, seconds=None, extra_fields=None):
    if extra_fields is None:
        extra_fields = {}
    if seconds is not None:
        extra_fields['seconds'] = seconds
    write_points([{
        'measurement': 'karrot.periodic',
        'tags': {
            'name': name,
        },
        'fields': {
            'value': 1,
            **extra_fields
        },
    }])


class timer:
    def __enter__(self):
        self.start = default_timer()
        return self

    def __exit__(self, type, value, traceback):
        self.end = default_timer()

    @property
    def elapsed_seconds(self):
        if self.end is None:
            # if elapsed_seconds is called in the context manager scope
            return default_timer() - self.start
        else:
            # if elapsed_seconds is called out of the context manager scope
            return self.end - self.start
