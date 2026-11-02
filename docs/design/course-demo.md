# Optional course APIs

Set `HETEROES_COURSE_DEMO=1` to enable four extra routes on the `api` role. The default is off. The `all`, `devices`,
`storage` and `scheduler` roles never install them, even when this flag is set. These routes are separate from the
default product route inventory and must be explicitly forwarded by the course gateway.

The enabled API requires these settings:

| Setting                         | Purpose                                                                                |
| ------------------------------- | -------------------------------------------------------------------------------------- |
| `HETEROES_OIDC_ISSUER`          | Public realm issuer, also configurable through the ordinary private OIDC configuration |
| `HETEROES_OIDC_JWKS_URL`        | Internal JWKS URL, with the same ordinary private-configuration fallback               |
| `HETEROES_COURSE_STUDENTS_FILE` | Mounted JSON file containing the course student list                                   |
| `HETEROES_COURSE_STUDENTDB_URL` | Separate PostgreSQL student database URL with a role granted SELECT only               |

Invalid or missing enabled configuration fails startup with a generic configuration error. It does not print the URL
or credentials. Other roles and the disabled API do not initialize course identity or data access.

| Method/path        | Response                                                                                                       |
| ------------------ | -------------------------------------------------------------------------------------------------------------- |
| `GET /hello`       | `{"message":"Hello from App Server!"}`                                                                         |
| `GET /secure`      | Verified bearer token: `{"message":"Secure resource OK","preferred_username":"…"}`; missing/invalid token: 401 |
| `GET /student`     | Current list from the mounted JSON file                                                                        |
| `GET /students-db` | Rows with `id`, `student_id`, `fullname`, `dob`, `major`, ordered by `id`; dates use ISO format                |

`/secure` uses the existing bounded RS256/JWKS verifier with client ID `flask-app`. A token addressed only to
`heteroes-web` is rejected. The verifier accepts the client through `aud` or `azp`, verifies issuer and required expiry,
and applies the same 30-second clock tolerance. It does not create a product user, a local session or a lab membership.
The course identity exercise is independent of the lab's user-approval workflow.

The JSON file is read afresh on each request, with a 1-MiB bound and a required top-level list. File failures return a
generic 503. The MiniCloud fixture supplies the required five `id`/`name`/`major`/`gpa` records and marks unknown personal
details as sample data; the backend does not invent them.

Student SQL is owned by `repositories/course.py`. Each request opens a short-lived PostgreSQL connection, starts a
read-only transaction and issues one fixed SELECT. It never initializes product tables, acquires the lab's write lock
or accepts SQL from the request. Database credentials must use a separate SELECT-only role; student CRUD demonstrations
run through a different administrative role outside this API. Database failures return a generic 503. The student
database is a course dependency, so its outage does not change product `/readyz` or scheduler health.

Tests use generated RSA keys and a local JWKS HTTP server. The real PostgreSQL matrix additionally creates a separate
throwaway database and a UUID-owned read-only role, proves SELECT succeeds and INSERT is denied, checks date/order
serialization and confirms that only the student table exists there. Those fixtures do not prove a deployed Keycloak
realm or nginx gateway; MiniCloud acceptance supplies that evidence.
