import httpx


class RuntimeRejected(Exception):
    """The runtime definitively rejected a new configuration without launching it."""


class Runtime:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": "Bearer " + token}

    def request(self, method, path, body=None):
        with httpx.Client(timeout=100) as client:
            response = client.request(method, self.url + path, headers=self.headers, json=body)
            response.raise_for_status()
            return response.json()

    def capabilities(self):
        value = self.request("GET", "/capabilities")
        if value.get("controlApiVersion") != 1:
            raise RuntimeError("Incompatible runtime control API")
        return value

    def workers(self):
        return self.request("GET", "/workers")

    def submit(self, config):
        try:
            return self.request("POST", "/runs", config)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 422:
                raise RuntimeRejected(error.response.json().get("message", "Runtime rejected configuration")) from None
            raise

    def snapshot(self, run_id):
        return self.request("GET", "/runs/" + run_id)

    def cancel(self, run_id):
        return self.request("POST", "/runs/" + run_id + "/cancel")

    def artifact(self, run_id, name):
        with httpx.Client(timeout=120) as client:
            with client.stream("GET", self.url + f"/runs/{run_id}/artifacts/{name}", headers=self.headers) as response:
                response.raise_for_status()
                yield from response.iter_bytes(1024 * 1024)
