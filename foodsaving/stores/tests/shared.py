import requests


class CSRFSession(requests.Session):
    def __init__(self, host):
        super().__init__()
        self.host = host

    def request(self, method, url, **kwargs):
        url = self.host + url
        response = super().request(method, url, **kwargs)
        csrftoken = self.cookies['csrftoken']
        self.headers.update({'X-CSRFToken': csrftoken})
        return response
