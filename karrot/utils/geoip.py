from functools import lru_cache

from django.contrib.gis.geoip2 import GeoIP2, GeoIP2Exception
from geoip2.errors import AddressNotFoundError

try:
    geoip = GeoIP2()
except GeoIP2Exception:
    geoip = None


def geoip_is_available():
    return geoip is not None


def get_client_ip(request):
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0]
    else:
        return request.META.get("REMOTE_ADDR")


@lru_cache
def ip_to_city(ip):
    if not geoip_is_available():
        return None
    try:
        return geoip.city(ip)
    except AddressNotFoundError:
        return None


@lru_cache
def ip_to_lat_lon(ip):
    if not geoip_is_available():
        return None
    try:
        return geoip.lat_lon(ip)
    except AddressNotFoundError:
        return None
