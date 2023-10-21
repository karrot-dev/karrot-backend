import time
from math import floor

# how many seconds
EXTEND_PERIOD = 3600


class ExtendSessionMiddleware:
    """ Extend the session expiry periodically

    Django only saves the session when it's modified, the redis ttl is set
    when it's saved. We tend not to modify the session, so users get logged
    out after the session expiry duration (2 weeks default) even though they
    were active.

    There is the SESSION_SAVE_EVERY_REQUEST option, but we don't really need
    it saved EVERY request.

    So we have this middleground middleware :)

    We store a unix timestamp of when we want to next extend in the session
    and when we reach that time, set it again into the future.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.session:
            now = floor(time.time())
            extend_after = request.session.get('extend_after', None)
            if extend_after is None or now > extend_after:
                # the act of modifying it will cause it to save and reset the ttl
                request.session['extend_after'] = now + EXTEND_PERIOD
        return self.get_response(request)
