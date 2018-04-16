from json import dumps as dump_json

from rest_framework.views import exception_handler


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
