# Backup and first push (2026-10-20)

Step 1 of `docs/plan-r11-release.md`.

## What was done

- Secret scan of all history (`git log -p --all`, added lines only) for private-key headers, `HETEROES_LAB_ACCESS_TOKEN=`
  values, `sudo -S` / `echo <pw> |` patterns, literal `password`/`token`/`secret`/`api key` assignments with long
  values, GitHub/AWS/OpenAI-style keys, JWTs, tunnel credential files, and tracked `.env`/`.pem`/`.key` files.
  Result: **no real password, token or key**. Matches were all benign: the sudo password is only read from the
  environment (`HETEROES_SUDO_PASSWORD`, never a literal); `credentials-file` is a recovery/cloud option name;
  `HETEROES_TOKEN`/`clientToken` values are word-like test fixtures or a `SET_A_STABLE_UUID...` placeholder; `token_env`
  and `tokenizer_revision` are field names/hashes. Known and accepted by the owner: the private Tailscale IP
  `100.110.165.40` in evidence, and one expired `trycloudflare.com` quick-tunnel URL in the 2026-10-09 experiment.
- Owner confirmed in chat that pushing is fine (internal Tailscale IP). `origin` =
  `git@github.com:Anakonkai01/hetero-es.git`; remote `main` (2bd2073) is an ancestor of local `main`; `git push origin
  --all` created every local branch on the remote and rewrote none of the three pre-existing remote branches.
- Offline bundle: `/mnt/Archive-2tb/heteroes-local/backups/heteroes-2026-10-20.bundle` (Archive UUID
  10443D1F443D094C verified first), 194 033 138 bytes, `git bundle verify` OK ("complete history"),
  sha256 `9b9244507c0ea6383ea418fc40b20a64885c6a79209156f10696d8a0eda89f3b`. It was made at the plan-copy commit,
  before this README and the AGENTS.md rule update.

## What this does NOT show

- It does not show the GitHub repository's visibility; the owner decided pushing is acceptable without that check.
- The post-push `git ls-remote` comparison of every branch tip was not completed in this session (a remote read was
  blocked by the tool permission layer); the push output itself listed every branch as created, so the next session
  should re-run the comparison.
- The scan is pattern-based, so it cannot prove absence of every possible secret; binary blobs were not decoded.

## Addendum 2026-10-20 (evening): push completed and branch tips compared

- The owner ran `git push origin --all` in the session; the output was `Everything up-to-date`, so the two commits that
  were missing after the first push (`ad3f192` and `cf80a1e`) were already on the remote.
- Comparison made locally against the remote-tracking refs that the push handshake refreshes (no network read): all 38
  local branches (`refs/heads/*`) have exactly the same commit as `refs/remotes/origin/<name>`, none differs and there
  is no remote-only branch among the tracking refs. `feat/v3-audit-recovery` and `main` are at their local tips as of
  `cf80a1e`.
- What this still does NOT show: it is not a fresh `git ls-remote` (blocked by the tool permission layer earlier, not
  retried), so a change made on GitHub after the push would not appear here; the repository visibility
  (private/public) is still unchecked.
