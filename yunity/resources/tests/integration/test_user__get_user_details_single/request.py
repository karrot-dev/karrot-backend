from .initial_data import user

request = {
    "endpoint": "/api/user/{}".format(user.id),
    "method": "get"
}
