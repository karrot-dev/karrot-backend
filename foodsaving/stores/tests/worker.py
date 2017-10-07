from foodsaving.stores.tests.shared import CSRFSession


def do_requests_process(iq, oq, host, url, cookies, headers):
    client = CSRFSession(host)
    client.cookies = cookies
    client.headers.update(headers)

    for task in iter(iq.get, 'STOP'):
        response = client.post(url)
        oq.put((task, response))

    client.close()
