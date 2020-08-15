from json import dumps as dump_json

from django.db import transaction
from rest_framework.views import exception_handler


def on_transaction_commit(func):
    def inner(*args, **kwargs):
        transaction.on_commit(lambda: func(*args, **kwargs))

    return inner


def json_stringify(data):
    """
    :type data: object
    :rtype: str
    """
    # TODO remove this unused function
    return dump_json(data, sort_keys=True, separators=(',', ':')).encode("utf-8") if data else None


def custom_exception_handler(exc, context):
    # get the standard response first
    response = exception_handler(exc, context)

    # add in the error code so we can distinguish better in the frontend
    if hasattr(response, 'data') and 'detail' in response.data and hasattr(exc, 'default_code'):
        response.data['error_code'] = exc.default_code

    return response


def find_changed(obj, data_dict):
    """compare data_dict keys to object properties and return a dict of changed values"""
    return {key: value for (key, value) in data_dict.items() if getattr(obj, key) != value}
