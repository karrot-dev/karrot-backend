"""Middlewares for the influxdb_metrics app."""
# from https://github.com/bitlabstudio/django-influxdb-metrics

import inspect
import time

from django.utils.deprecation import MiddlewareMixin

from .influxdb_utils import write_points


class InfluxDBRequestMiddleware(MiddlewareMixin):
    """
    Measures request time and sends metric to InfluxDB.
    Credits go to: https://github.com/andymckay/django-statsd/blob/master/django_statsd/middleware.py#L24  # NOQA
    """
    def process_view(self, request, view_func, view_args, view_kwargs):
        view = view_func
        if not inspect.isfunction(view_func):
            view = view.__class__
        try:
            request._view_module = view.__module__
            request._view_name = view.__name__
            request._start_time = time.time()
        except AttributeError:  # pragma: no cover
            pass

    def process_response(self, request, response):
        self._record_time(request)
        return response

    def process_exception(self, request, exception):
        self._record_time(request)

    def _record_time(self, request):
        if hasattr(request, '_start_time'):
            ms = int((time.time() - request._start_time) * 1000)

            is_authenticated = False
            is_staff = False
            is_superuser = False
            if request.user.is_authenticated:
                is_authenticated = True
                if request.user.is_staff:
                    is_staff = True
                if request.user.is_superuser:
                    is_superuser = True

            resolver_match = request.resolver_match
            view_name = resolver_match.view_name

            data = [{
                'measurement': 'django_request',
                'tags': {
                    'is_authenticated': is_authenticated,
                    'is_staff': is_staff,
                    'is_superuser': is_superuser,
                    'method': request.method,
                    'module': request._view_module,
                    'view': request._view_name,
                    'view_name': view_name,
                },
                'fields': {
                    'value': ms,
                    'url': request.get_full_path(),
                },
            }]
            write_points(data)
