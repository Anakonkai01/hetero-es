import httpx


class RuntimeRejected(Exception):
    """The runtime definitively rejected a new configuration without launching it."""


class Runtime:
    def __init__(self, url, token):
        self.url = url.rstrip("/")
        self.headers = {"Authorization": "Bearer " + token}

    def request(self, method, path, body=None, timeout=100):
        with httpx.Client(timeout=timeout) as client:
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

    def runs(self):
        return self.request('GET','/runs')

    def maintenance(self):
        return self.request('GET','/maintenance')['hold']

    def acquire_maintenance(self):
        return self.request('POST','/maintenance/acquire',{})

    def release_maintenance(self,maintenance_id):
        return self.request('POST','/maintenance/release',{'maintenanceId':maintenance_id})

    def backup(self,maintenance_id):
        return self.request('POST','/backups',{'maintenanceId':maintenance_id},timeout=1800)

    def backup_stream(self,backup_id):
        with httpx.Client(timeout=1800) as client:
            with client.stream('GET',self.url+'/backups/'+backup_id,headers=self.headers) as response:
                response.raise_for_status()
                yield from response.iter_bytes(1024*1024)

    def discard_backup(self,backup_id):
        return self.request('DELETE','/backups/'+backup_id)

    def artifact(self, run_id, name):
        with httpx.Client(timeout=120) as client:
            with client.stream("GET", self.url + f"/runs/{run_id}/artifacts/{name}", headers=self.headers) as response:
                response.raise_for_status()
                yield from response.iter_bytes(1024 * 1024)
