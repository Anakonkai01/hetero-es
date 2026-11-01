# OIDC sign-in and local mode

`HETEROES_AUTH_MODE=local` remains the default. `oidc` selects an explicit public `HETEROES_OIDC_ISSUER` and internal
`HETEROES_OIDC_JWKS_URL`; factory arguments/config keys are available too. Issuer and JWKS URLs have no credentials,
query or fragment. The public issuer must exactly match Keycloak's token issuer; the internal JWKS address can use its
container hostname. Cloud Python dependencies live in `backend/requirements-cloud.lock.txt`; desktop/local runtime
imports do not import PyJWT or cryptography. Install the cloud lock in the development backend environment to run all
OIDC tests. The packaged desktop profile keeps its separate dependency list.

The verifier fixes RS256, requires issuer/subject/expiry, verifies optional nbf and allows30 seconds of clock skew.
Audience contains `heteroes-web` or authorized party (`azp`) equals it. Numeric times and nonempty identity strings are
validated. JWKS retrieval ignores environment proxies, refuses every redirect, times out after5 seconds and reads at
most256 KiB. It accepts at most32 keys, with unique bounded IDs, signing/verification purpose and RSA keys of at least
2048 bits. Successful keys expire after300 seconds. A first unknown-key rotation refreshes immediately; further unknown
refreshes are bounded to once per5 seconds, with at most64 negative IDs retained for30 seconds. Failed fetches also
have a5-second retry bound. Expired cache entries fail closed. A flood may delay another rotation until the short retry
window ends. Public authentication errors never include the bearer, library exception or provider response.

Identity is `kc:<sub>`, with `preferred_username` as the username. A collision with another subject/local account returns
409 and never links the accounts. New ordinary users are PENDING. A new realm `lab-admin` is ACTIVE, a platform admin,
may create workspaces and receives ADMIN membership of the initial lab. Subsequent sign-in preserves durable approval
and profile edits, updates the username, and derives platform permission from the current token's role plus ACTIVE
status. It never revives a suspended/rejected account. No cloud password users are seeded; identity rows carry an
unusable password sentinel. Local authentication treats that sentinel as invalid credentials.

```mermaid
sequenceDiagram
  Browser->>Web: Read /config.json before session query
  Browser->>Keycloak: Authorization Code + PKCE
  Keycloak-->>Browser: Code + state callback
  Browser->>Keycloak: Code + verifier
  Keycloak-->>Browser: Access/refresh/ID tokens
  Browser->>Browser: Memory user store; erase callback query
  Browser->>API: Bearer access token
  API->>Keycloak: Bounded internal JWKS (cached)
  API->>DB: Identity + fresh approval/membership
  API-->>Browser: Existing session DTO (no JWT)
```

In OIDC mode local login/register/password/revoke-other-sessions return guided404 responses before body/auth validation.
The session endpoint uses verified JWTs. Device token enrollment/polling/authentication remains separate. Administrative
session revocation for identity users points to HeteroES ID rather than claiming that deleting local session rows
revoked an external session. Logout invalidates download tickets bound to the presented token, and the frontend performs
provider end-session logout. Offline JWT validation cannot immediately observe Keycloak session/role revocation: an
already issued token remains valid until its expiry (plus the defined clock skew); keep provider access-token lifetimes
short. Product account suspension/membership changes are checked from durable state on protected operations.

Recovery download tickets store an `oidc:`-prefixed token digest, never the raw token. Expiry is the earlier of60 seconds
and the JWT's actual expiry; an already expired token cannot mint one during clock leeway. Consumption requires the
single-use cookie capability and rechecks durable approval, workspace membership and run ownership. Local tickets keep
their existing live-session-row check. Restore deletes sessions and download tickets together with enabling dispatch
hold. Existing schema columns suffice; no JWT/session persistence table is introduced.

The web reads `/config.json` before rendering its session provider. Its nonsecret shape is:

```json
{
  "authMode": "oidc",
  "basePath": "/lab/",
  "issuer": "https://cloud.example/auth/realms/realm_523h0164",
  "clientId": "heteroes-web"
}
```

The default static config selects local mode. `HETEROES_WEB_BASE=/lab/` sets built asset URLs for a gateway subpath;
`basePath` sets the browser router/callback paths at runtime. Deployment can mount a config without rebuilding for a
new issuer/host. Use a public PKCE client with exact allowed callback/silent/logout URLs under that base. Browser PKCE
needs HTTPS outside localhost; public EC2 HTTP alone is insufficient.

`oidc-client-ts` uses code flow, PKCE and automatic silent renewal. Its user store is memory-only; only unfinished PKCE
transaction state/verifiers use sessionStorage. OIDC selection clears an old local token before any session request.
Access-token load/expiry updates the API client and invalidates scoped query data. Callback query data is erased on
success and error. A reload recovers SSO through a silent code flow; logout uses the provider end-session endpoint.
Local password/registration/security UI is replaced in OIDC mode. Local token persistence remains unchanged.

Verification uses generated RSA keys and actual loopback JWKS HTTP; both database dialects exercise account and recovery
authorization. `node scripts/check-web-oidc.mjs <fresh-output>` runs Chromium and the actual OIDC library against an
owned ephemeral protocol fixture: code/verifier matching, refresh grant, memory-only tokens, SSO reload and end-session.
It records only safe counters/receipt and a signed-in screenshot, no HAR/token/code logs. An early probe's claimed
refresh had counter0; it is rejected. The final probe explicitly awaits counter advancement and asserts it again in the
final receipt; zero/missing counters have independent regressions. This fixture is not actual Keycloak deployment;
MiniCloud C owns that acceptance. The ordinary local-mode browser/Electron checks remain mandatory.

Primary APIs: [PyJWT decode](https://pyjwt.readthedocs.io/en/stable/api.html),
[oidc-client-ts settings](https://authts.github.io/oidc-client-ts/classes/UserManagerSettingsStore.html),
[UserManager](https://authts.github.io/oidc-client-ts/classes/UserManager.html).
