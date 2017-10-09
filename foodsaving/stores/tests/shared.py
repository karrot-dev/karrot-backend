import requests


class CSRFSession(requests.Session):
    def __init__(self, host):
        super().__init__()
        self.host = host

    def request(self, method, url, **kwargs):
        # apply hostname before every request
        url = self.host + url

        response = super().request(method, url, **kwargs)

        # refresh CSRF token
        csrftoken = self.cookies.get('csrftoken', '')
        self.headers.update({'X-CSRFToken': csrftoken})
        return response

    def login(self, email, password):
        # first do some request to get the CSRF token
        self.get('/api/auth/status/')
        return self.post('/api/auth/', json={'email': email, 'password': password})
