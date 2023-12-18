"""Utilities for working with influxdb."""
# partially from https://github.com/bitlabstudio/django-influxdb-metrics
import logging
from threading import Thread

from django.conf import settings
from django.core.signals import request_finished
from django.dispatch import receiver
from influxdb import InfluxDBClient

logger = logging.getLogger(__name__)


def get_client():
    """Returns an ``InfluxDBClient`` instance."""
    return InfluxDBClient(
        settings.INFLUXDB_HOST,
        settings.INFLUXDB_PORT,
        settings.INFLUXDB_USER,
        settings.INFLUXDB_PASSWORD,
        settings.INFLUXDB_DATABASE,
        timeout=settings.INFLUXDB_TIMEOUT,
        ssl=getattr(settings, "INFLUXDB_SSL", False),
        verify_ssl=getattr(settings, "INFLUXDB_VERIFY_SSL", False),
    )


def query(query):
    """Wrapper around ``InfluxDBClient.query()``."""
    client = get_client()
    return client.query(query)


def actually_write_points(data):
    """
    Writes a series to influxdb.
    :param data: Array of dicts, as required by
      https://github.com/influxdb/influxdb-python
    """
    if getattr(settings, "INFLUXDB_DISABLED", False):
        return

    client = get_client()
    use_threading = getattr(settings, "INFLUXDB_USE_THREADING", False)
    if use_threading is True:
        thread = Thread(
            target=process_points,
            args=(
                client,
                data,
            ),
        )
        thread.start()
    else:
        process_points(client, data)


def process_points(client, data):
    """Method to be called via threading module."""
    try:
        client.write_points(data)
    except Exception:
        if getattr(settings, "INFLUXDB_FAIL_SILENTLY", True):
            logger.exception("Error while writing data points")
        else:
            raise


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
        actually_write_points(batch)
        batch_count = 0
        batch.clear()
