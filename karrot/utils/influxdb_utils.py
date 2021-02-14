from django.core.signals import request_finished
from django.dispatch import receiver
from influxdb_metrics.loader import write_points as actually_write_points

# we batch writes for more efficiency, in one of two contexts:
# - per request (think: web requests)
# - per minute (think: huey)

batch_count = 0
batch = []


def write_points(points):
    global batch_count
    batch_count += 1
    batch.extend(points)


@receiver(request_finished)
def on_request_finished(sender, **kwargs):
    if len(batch) > 0:
        flush_stats()


def flush_stats():
    global batch_count
    if len(batch) > 0:
        print('writing batch!', len(batch), 'points from', batch_count, 'batches')
        actually_write_points(batch)
        batch_count = 0
        batch.clear()
