"""`GET /v1/updates/{sha256}`: the small message (a generation record) with which a worker can replay an update instead of downloading 1 GB."""
import pytest

from heteroes.http_transport import CoordinatorServer, HttpClient, TransportError

PARENT, CHILD = "a" * 64, "b" * 64
UPDATE = {"record_json": "{}", "record_hash": "c" * 64, "child_weights_sha256": CHILD}


@pytest.fixture
def server(tmp_path):
    server = CoordinatorServer(api=None, job=None, models_dir=tmp_path)
    server.start()
    yield server
    server.stop()


def test_the_update_of_a_known_parent_is_served(server):
    server.updates[PARENT] = UPDATE
    assert HttpClient(server.url, retries=0).get_update(PARENT) == UPDATE


def test_an_unknown_parent_gives_none(server):
    assert HttpClient(server.url, retries=0).get_update(PARENT) is None


def test_a_name_that_is_not_a_hash_gives_none(server):
    server.updates["../x"] = UPDATE
    assert HttpClient(server.url, retries=0).get_update("../x") is None


def test_the_route_needs_the_token_when_the_server_has_one(tmp_path):
    from heteroes.http_transport import UnauthorizedError
    server = CoordinatorServer(api=None, job=None, models_dir=tmp_path, token="secret")
    server.start()
    try:
        server.updates[PARENT] = UPDATE
        with pytest.raises(UnauthorizedError):
            HttpClient(server.url, retries=0).get_update(PARENT)
        assert HttpClient(server.url, token="secret", retries=0).get_update(PARENT) == UPDATE
    finally:
        server.stop()


def test_post_to_the_route_is_refused(server):
    import urllib.error
    import urllib.request
    request = urllib.request.Request(server.url + f"/v1/updates/{PARENT}", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as caught:
        urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=5)
    assert caught.value.code == 405
