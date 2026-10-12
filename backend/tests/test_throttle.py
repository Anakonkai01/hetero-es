"""Password guessing and registration spam are slowed down; the real caller is found behind a local proxy."""
from fastapi.testclient import TestClient
import pytest

from backend.app import create_app
from backend.throttle import Throttle, client_address
from test_api import Runtime


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_throttle_blocks_after_the_limit_and_forgives_after_the_window():
    clock = Clock()
    throttle = Throttle(limit=3, window=60, clock=clock)
    for _ in range(3):
        assert throttle.retry_after('k') == 0
        throttle.record('k')
    assert 0 < throttle.retry_after('k') <= 60
    assert throttle.retry_after('other') == 0
    clock.now += 61
    assert throttle.retry_after('k') == 0


def test_the_wait_ends_when_the_oldest_attempt_leaves_the_window():
    clock = Clock()
    throttle = Throttle(limit=2, window=100, clock=clock)
    throttle.record('k'); clock.now += 30; throttle.record('k')
    assert throttle.retry_after('k') == 70


def test_the_wait_is_rounded_up_never_down():
    clock = Clock()
    throttle = Throttle(limit=1, window=100, clock=clock)
    throttle.record('k'); clock.now += 30.5
    assert throttle.retry_after('k') == 70       # 69.5 s remain


def test_clear_forgets_a_key_and_memory_does_not_grow_without_bound():
    clock = Clock()
    throttle = Throttle(limit=2, window=60, clock=clock)
    throttle.record('k'); throttle.record('k'); throttle.clear('k')
    assert throttle.retry_after('k') == 0
    for number in range(500):
        throttle.record(('guess', number))
    clock.now += 61
    throttle.record('trigger')
    assert len(throttle.attempts) <= 2


@pytest.mark.parametrize('peer,headers,expected', [
    ('127.0.0.1', {'CF-Connecting-IP': '203.0.113.9'}, '203.0.113.9'),
    ('100.110.165.40', {'CF-Connecting-IP': '203.0.113.9'}, '203.0.113.9'),
    ('192.168.1.5', {'X-Forwarded-For': '198.51.100.7, 10.0.0.1'}, '198.51.100.7'),
    ('127.0.0.1', {'CF-Connecting-IP': '203.0.113.9', 'X-Forwarded-For': '198.51.100.7'}, '203.0.113.9'),
    ('8.8.8.8', {'CF-Connecting-IP': '203.0.113.9'}, '8.8.8.8'),           # a public peer cannot choose its identity
    ('127.0.0.1', {'CF-Connecting-IP': 'not an address'}, '127.0.0.1'),
    ('127.0.0.1', {}, '127.0.0.1'),
    ('testclient', {'CF-Connecting-IP': '203.0.113.9'}, 'testclient'),
    (None, {}, 'unknown'),
])
def test_client_address_trusts_forwarding_headers_only_from_a_local_proxy(peer, headers, expected):
    assert client_address(peer, headers) == expected


@pytest.fixture
def lab(tmp_path):
    app = create_app(tmp_path / 'state.sqlite', {'admin': 'test-admin-pass'}, Runtime(), dispatch=False)
    clock = Clock()
    app.state.login_failures = Throttle(5, 600, clock)
    app.state.login_failures_by_address = Throttle(30, 600, clock)
    app.state.registrations = Throttle(10, 3600, clock)
    with TestClient(app) as client:
        yield client, clock


def sign_in(client, username='admin', password='test-admin-pass', **headers):
    return client.post('/api/v1/auth/login', json={'username': username, 'password': password}, headers=headers)


def test_five_wrong_passwords_lock_that_caller_out_even_for_the_right_password(lab):
    client, clock = lab
    for _ in range(5):
        assert sign_in(client, password='wrong-password').status_code == 401
    blocked = sign_in(client)
    assert blocked.status_code == 429 and int(blocked.headers['Retry-After']) > 0
    assert 'Too many' in blocked.json()['message']
    clock.now += 601
    assert sign_in(client).status_code == 200


def test_a_successful_sign_in_forgets_earlier_mistakes(lab):
    client, _ = lab
    for _ in range(4):
        sign_in(client, password='wrong-password')
    assert sign_in(client).status_code == 200
    for _ in range(4):
        assert sign_in(client, password='wrong-password').status_code == 401
    assert sign_in(client).status_code == 200


def test_unknown_users_are_throttled_like_known_ones(lab):
    client, _ = lab
    for _ in range(5):
        assert sign_in(client, username='nobody', password='guess').status_code == 401
    assert sign_in(client, username='nobody', password='guess').status_code == 429


def test_one_address_trying_many_usernames_is_stopped_as_a_whole(lab):
    client, _ = lab
    for number in range(30):
        assert sign_in(client, username=f'user{number}', password='guess').status_code == 401
    assert sign_in(client, username='another', password='guess').status_code == 429
    assert sign_in(client).status_code == 429


def test_an_attacker_cannot_lock_the_owner_out_from_another_address(tmp_path):
    app = create_app(tmp_path / 'state.sqlite', {'admin': 'test-admin-pass'}, Runtime(), dispatch=False)
    with TestClient(app, client=('127.0.0.1', 50000)) as client:
        attacker = {'CF-Connecting-IP': '203.0.113.9'}
        owner = {'CF-Connecting-IP': '198.51.100.7'}
        for _ in range(5):
            assert sign_in(client, password='wrong-password', **attacker).status_code == 401
        assert sign_in(client, **attacker).status_code == 429
        assert sign_in(client, **owner).status_code == 200


def test_registration_is_limited_per_address(lab):
    client, clock = lab
    def register(number):
        return client.post('/api/v1/auth/register', json={'username': f'person{number}', 'password': 'a-long-enough-password', 'displayName': 'P'})
    for number in range(10):
        assert register(number).status_code == 201
    blocked = register(99)
    assert blocked.status_code == 429 and 'Retry-After' in blocked.headers
    clock.now += 3601
    assert register(100).status_code == 201


def test_interactive_api_documentation_is_not_public_when_the_web_app_is_served(tmp_path):
    web = tmp_path / 'web'; (web / 'assets').mkdir(parents=True); (web / 'index.html').write_text('<html>Lab UI</html>')
    app = create_app(tmp_path / 'state.sqlite', {'admin': 'test-admin-pass'}, Runtime(), dispatch=False, web_directory=web)
    with TestClient(app) as client:
        for path in ('/docs', '/redoc', '/openapi.json'):
            assert 'swagger' not in client.get(path).text.lower() and '"openapi"' not in client.get(path).text
    open_app = create_app(tmp_path / 'state2.sqlite', {'admin': 'test-admin-pass'}, Runtime(), dispatch=False)
    with TestClient(open_app) as client:
        assert client.get('/openapi.json').status_code == 200      # development keeps its documentation
