# M2 cloud setup and operation

Status: code and local evidence are ready; no cloud resources have been created.
The owner has no cloud accounts yet. [m2-implementation.md](m2-implementation.md)
records what has actually passed; [lab-roadmap.md](lab-roadmap.md) is the accepted
scope. Commands below are an operator workflow, not a deployment already performed.

## First create the three accounts

1. Create an AWS account and select **Free Plan**. In Billing, record the actual
   plan, remaining credits and expiry. Keep the plan FREE; this project does not
   authorize a Paid upgrade. Check alerts and the live CPU/EBS/public-IPv4/transfer
   estimate before creating an instance. Do not assume a fixed USD credit balance
   or the earlier illustrative monthly price.
   [AWS plan documentation](https://docs.aws.amazon.com/awsaccountbilling/latest/aboutv2/free-tier-plans.html).
2. Create a Cloudflare account and activate R2 after reviewing its billing terms.
   Create one **private Standard** bucket, with public development URL/custom-domain
   access disabled. Generate an **Object Read & Write** S3 token scoped to that
   bucket; save the access key, secret and S3 endpoint directly into the private
   local file described below. This is different from a general Cloudflare REST
   bearer token. [R2 setup](https://developers.cloudflare.com/r2/get-started/s3/),
   [R2 authentication](https://developers.cloudflare.com/r2/api/tokens/).
3. Sign in to [DuckDNS](https://www.duckdns.org/), choose an available subdomain
   and keep its update token private. It provides the fixed management hostname;
   Caddy supplies HTTPS. The chosen name is not provisioned by this repository.

R2 free allowances apply to the account, not separately to this project. Use a
dedicated account for the trial or review all account usage before setting
`exclusiveAccountConfirmed` to true. The project's 8 GB and request limits are
application controls; unrelated tools/accounts must not use the same allowances
without review. [R2 pricing](https://developers.cloudflare.com/r2/pricing/).

Never paste cloud keys/passwords into chat, Git, argv or screenshots. Use provider
login or a private editor/file. The local M1 admin password stays as configured;
the exported cloud admin is independently generated and at least 12 characters.

## Private files and preflight — on the 5070 Ti development machine

The existing staging files are `~/.config/heteroes-m2/`, mode 700/600. Create a
separate **new** export for the eventual cloud cutover; do not deploy a moving
SQLite database by copying its live file. Use the backend interpreter from Track B.

```bash
mkdir -p "$HOME/.config/heteroes-cloud"
chmod 700 "$HOME/.config/heteroes-cloud"
cp deploy/r2.example.json "$HOME/.config/heteroes-cloud/r2.json"
chmod 600 "$HOME/.config/heteroes-cloud/r2.json"
```

Edit that private `r2.json` with the actual endpoint, bucket and scoped S3 keys.
Configure an AWS profile `heteroes-m2` through the official AWS CLI/provider
login, or the private AWS credentials files. Keep root keys out of the application.
The Python preflight uses Boto3's standard profile resolution.

```bash
AWS_EC2_METADATA_DISABLED=true .venv-backend/bin/python scripts/cloud-preflight.py \
  --profile heteroes-m2 --r2-config "$HOME/.config/heteroes-cloud/r2.json"
```

Proceed only when the live Free Tier API reports active FREE, credits remaining,
future expiry and an eligible preferred x86 `t3.small` or fallback `t3.micro`.
No resources are created by preflight. An absent profile, denied API permission
or unsupported type is a failing gate, never a reason to upgrade plans.

## R2 acceptance before provisioning the CPU server

Keep M2 dispatch held. Add `storageFile` pointing to the private R2 file in
`~/.config/heteroes-m2/config.json`, then restart only its isolated backend. The
main M1 dispatcher can remain online while all M2 agents stay stopped. Sign in
to the isolated M2 UI with its private credentials; Operations should report
cloud storage configured. R2 keys never go to a GPU agent.

The selected M1 point has already been exported at:

```text
~/.local/share/heteroes-integration/runs/096b09ec03ab4d8b9ca189596593db3a/recovery-points/b2177db16d614cdcaf2021963d411140
```

Its two canonical weight objects are about 1.98 GB in total. Upload/copy headroom
is reserved before signed rights are issued. Do not upload the complete 33.6 GB
M1 archive to the trial bucket. To import the selected point:

```bash
.venv-backend/bin/python scripts/cloud-recovery.py import \
  --url http://100.110.165.40:8002 --workspace lab \
  --runtime-root ../hetero-es-integration \
  --credentials-file "$HOME/.config/heteroes-m2/credentials.json" \
  --point "$HOME/.local/share/heteroes-integration/runs/096b09ec03ab4d8b9ca189596593db3a/recovery-points/b2177db16d614cdcaf2021963d411140"
```

The command uploads directly to private signed URLs, asks the CPU backend to
read/hash the objects, publishes the manifest last and waits for READY. Historical
import requires both platform administration and scoped experiment access; its
final SHA must match the preserved M1 experiment. It does not launch a GPU.

Then restore from **cloud**, with no dependency on the source point:

```bash
.venv-backend/bin/python scripts/cloud-recovery.py restore \
  --url http://100.110.165.40:8002 --workspace lab \
  --runtime-root ../hetero-es-integration \
  --credentials-file "$HOME/.config/heteroes-m2/credentials.json" \
  --point-id b2177db16d614cdcaf2021963d411140 \
  --destination "$HOME/.local/share/heteroes-m2/r2-restored-m1"
```

Check that the final SHA equals
`987541249378460c668ff9865cbcc5823331eddae4bdfbebd87a532977b96c38`, the directory
is new/held and no PID was restored. Test missing/corrupt cloud data in an isolated
test point; never damage the retained M1 point to perform a fault test. A standalone
restored directory is an inspection/recovery artifact, not authorization to start
a second coordinator. Resuming interrupted compute requires the original assignment,
its device identity and confirmed former process shutdown; there is no automatic
cross-device failover in M2.

## Prepare and review EC2

Use Singapore if permitted by the actual account. Prepare an existing default
public subnet, a dedicated security group exposing only 80/443 and SSH from the
operator's address, and a user-owned SSH key. The script creates exactly one CPU
instance after the review gates; no NAT gateway, load balancer or managed database.
Resolve a current Canonical Ubuntu 24.04 amd64 EBS AMI in that region using
[Canonical's official instructions](https://ubuntu.com/aws/docs/aws-how-to/instances/find-ubuntu-images/).

Copy `deploy/ec2.example.json` to a private file and fill its actual AMI, subnet,
group, key name and stable client token. Review the live price and alerts before
setting the two confirmation fields. CPU credits are forced to **standard**;
the root EBS volume is encrypted gp3, initially 20 GiB and bounded to 30 GiB.

```bash
.venv-backend/bin/python scripts/provision-m2-ec2.py plan \
  --profile heteroes-m2 --config "$HOME/.config/heteroes-cloud/ec2.json"
.venv-backend/bin/python scripts/provision-m2-ec2.py apply \
  --profile heteroes-m2 --config "$HOME/.config/heteroes-cloud/ec2.json"
```

Apply repeats the live gates. Its stable EC2 client token makes a lost-response
retry idempotent. Record the instance identity; stop if a different resource or
plan is requested. Inspect the actual account allowance rather than relying on
an instance-name assumption.

## Build, export and install — only at confirmed idle cutover

The old M1 controller must be held before any M2 GPU is enabled. Confirm all
old selected processes stopped, hold dispatch and acquire its runtime maintenance
hold as in [lab-operations.md](lab-operations.md). Stop the old controller before
handing these physical GPUs to the cloud deployment. Preserve its rollback data.

Export the current idle product metadata into a **new** directory using a consistent
SQLite backup. This keeps IDs/FIFO/accounts, revokes sessions, holds dispatch and
generates an independent cloud admin; it does not copy old process identities.

```bash
.venv-backend/bin/python scripts/prepare-m2.py \
  --source-db "$HOME/.local/share/heteroes-integration/product/product.sqlite" \
  --destination "$HOME/.config/heteroes-cloud/export"
.venv-backend/bin/python scripts/build-m2-release.py \
  --output "$HOME/.local/share/heteroes-m2/heteroes-cpu-release.tar.gz"
```

If continuing the staging M2 history, use its idle database instead of M1; the
script refuses unresolved M2 reservations. Never downgrade new history to M1.
Copy the private R2 file into `export/r2.json`, mode 600. Transfer the release and
private export over SSH/SCP to the new EC2. Verify the printed release SHA and
extract into a new directory before installation.

On the **new Ubuntu CPU server**, set DuckDNS to its public IPv4. Alternatively,
run `scripts/update-duckdns.py --private-config /private/duckdns.json` there; that
file has `subdomain` and `token`. A blank IP uses the requesting server's IPv4.
[DuckDNS update specification](https://www.duckdns.org/spec.jsp).

```bash
sudo bash /private/release/deploy/install-cpu-server.sh \
  /private/release /private/export YOUR_SUBDOMAIN.duckdns.org
```

The installer uses the [official Caddy packages](https://caddyserver.com/docs/install),
one CPU-only backend and the real production frontend. Internal API port 8000
binds loopback; 80/443 serve the fixed management address. The installer refuses
an existing `/opt/heteroes`; it is for a fresh server. Queue remains held. Check
`systemctl status heteroes caddy`, HTTPS health/login, imported history and storage
before enabling any GPU. Keep the private export credentials available to the
owner; they differ from the local M1 admin.

## Agents and final acceptance

The isolated agent sources are already installed on the 5070 Ti, Quang's 3060
and `thao_nguyen@100.92.20.58`. Existing environments/drivers/repos were preserved.
Update each private agent `serverUrl` to the HTTPS management address. Device
tokens from staging work only with a database containing those same identities;
a fresh M1 export instead requires a new pairing/real self-test/admin approval.
Use a private compute address and ensure workers can reach it through Tailscale.

Start one agent per device in its isolated environment:

```bash
PYTHONPATH=/path/to/isolated/runtime/src /path/to/isolated/python \
  -m heteroes.product.agent run --config /private/agent/config.json
```

It boots OFF. In **Workers**, explicitly enable the current boot as the GPU owner,
or run the agent CLI `on`/`off` and sign in when prompted. Platform admin approval
is separate. Choose an explicit coordinator and selected candidate workers on the
experiment form. Owners can turn off and drain; an offline device is not released.

Resume reviewed cloud dispatch only after the old controller is stopped. Submit
the short three-device acceptance within the remaining **0.083799 GPU-hours** of
the M2 cap, close the browser, and verify all three machines commit candidates.
Check cloud READY points, checksum restore, public HTTPS browser behavior and
release after all selected child processes stop. Record new cloud evidence before
marking M2 complete. Existing local tests are insufficient for that gate.

Metadata restore uses `scripts/restore-m2-metadata.py --database ... --manifest ...
--destination NEW_DIRECTORY`. It verifies the consistent downloaded database,
holds dispatch, revokes sessions and rotates the cloud admin, while preserving
device identities and unknown reservations. It never silently grants a new
coordinator ownership. Keep private device configs as part of the operator's
credential recovery, outside Git and separately from ordinary experiment exports.

For an upgrade, hold dispatch, confirm all GPU shutdowns, stop the CPU service,
take a consistent metadata backup and deploy the reviewed release. Preserve the
latest held M2 database on rollback; the M1 runtime refuses an agent-mode database.
Do not apply the fresh-server installer over a running installation.
