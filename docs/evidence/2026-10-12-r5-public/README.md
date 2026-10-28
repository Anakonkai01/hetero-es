# Public r5 deployment — 2026-10-12

The owner requested a website download flow for other computers. The live lab
had no active experiments or device/physical reservations. A private online
SQLite snapshot passed `integrity_check` before the managed restart; its path is
`~/.local/share/heteroes-session-archives/r5-public-20261012T130611Z/`.

The backend was restarted only through `scripts/local-lab.py`, which held and
reopened the previously open idle queue. No GPU process was started. Installers
were published with the existing prepared receipt; no build was regenerated.

`installers-published.json` records the reviewed published inventory.
`public-download-verification.json` records HTTP 200 for the homepage and health,
the live `deviceConfiguration` capability, r5 public manifest, and full streamed
downloads of all four installers with matching sizes and SHA-256 hashes.
`browser-download-page.json` and `landing-downloads.png` check the rendered
public page's four r5 download links using a fresh headless browser session.

The earlier source, package and CPU validation remains under
`../2026-10-12-lf1-codex/`. No credentials or raw private configuration are included
in this evidence folder.

## What this does NOT show

This does not prove native Windows installation, native Linux desktop launch,
GPU compatibility, a two-machine job or a worker on another network. Public
download verification ran from the host through the public HTTPS endpoint.
Automatic public compute routing to a newly selected coordinator remains missing.
