# Deploying the server (AWS and Google Cloud)

Two **independent** deployments of the same image: `aws/` and `gcp/` are two Terraform folders, each with its own
provider, credentials and state (S3 for AWS, GCS for Google Cloud). An `apply` or a `destroy` on one side never
touches the other. Shared: the image (`../Dockerfile`) and `publish.sh [aws|gcp|both] [all|image|data]`.

The interface (`../../ui`) is static and served by Cloudflare (see [Interface](#interface-cloudflare)).

## Addresses

| | URL |
|---|---|
| Site (interface, Cloudflare) | https://astrowrap.earth (and `www.`) |
| API (AWS) | https://api.astrowrap.earth/api/health |
| API documentation | https://api.astrowrap.earth/docs |
| API (Google Cloud) | https://api-gcp.astrowrap.earth/api/health |
| Fallback without DNS | `terraform -chdir=aws output url_fallback` (an `<ip-with-dashes>.sslip.io` address) |

The domain's DNS is on **Cloudflare** (free plan). Each cloud has a fixed IP; Caddy serves the domain and the
sslip.io fallback over HTTPS (Let's Encrypt). The API only accepts calls from the site (`cors`).

| Name | Type | Value | Proxy |
|---|---|---|---|
| `api` | A | `terraform -chdir=aws output ip` | **DNS only** (grey cloud): Caddy does the HTTPS |
| `api-gcp` | A | `terraform -chdir=gcp output ip` | **DNS only** |
| `@`, `www` | created by `wrangler deploy` (custom domains of the `astrowrap` Worker) | | proxied |

## Private settings

Nothing that identifies the accounts is in the repository. Each folder needs two files, ignored by git:

| File | Content | Template |
|---|---|---|
| `backend.hcl` | state bucket and key (AWS) or prefix (GCP) | `backend.hcl.example` |
| `terraform.tfvars` | `name` (base name of the resources), alert email; GCP: `project`, `billing_account`, `data_device_name` | see `variables.tf` |

`name` has no default on purpose: without `terraform.tfvars`, `plan` fails instead of proposing to replace
everything. Keep a copy of both files next to the state (in the state bucket) and restore them before any `apply`
on a new clone:

```bash
terraform -chdir=aws init -backend-config=backend.hcl
terraform -chdir=gcp init -backend-config=backend.hcl
```

The state buckets (versioned, private, native locking) are created by hand, **outside Terraform**, so that a
`terraform destroy` cannot take them away. Do not delete them.

## Architecture

```
AWS (ca-central-1)
Internet ──80/443──> EC2 t4g.small (Amazon Linux 2023 arm64, Auto Scaling group of 1 machine)
                      ├─ Caddy (HTTPS, proxy)  ──>  server container (uvicorn, 1 process)
                      └─ /data: EBS gp3 disk, kept when the machine is replaced
                           ├─ app/pretreatment_data/   Parquet files, synced from S3 at boot
                           ├─ app/cache/               Natural Earth, relief, saved areas
                           ├─ caddy/                   certificates
                           └─ swapfile                 2 GB
S3   <name>-…/pretreatment_data/   the Parquet files (source of truth, ~1 GB)
ECR  <name>:latest                 the image (2 images kept)
CloudWatch  /<name> (logs), health alarm; SNS (email); budget

Google Cloud (northamerica-northeast1)
Internet ──80/443──> VM e2-standard-2 (Debian 12, x86, 8 GB), managed group of 1 machine
                      ├─ Caddy  ──>  server container (DuckDB 3 GB, 2 threads)
                      └─ /data: stateful pd-balanced disk (same layout)
GCS                <name>-<project number>/pretreatment_data/
Artifact Registry  …-docker.pkg.dev/<project>/<name>/server:latest
Cloud Logging / Monitoring: logs, uptime check, email alert; budget in steps
```

**Data.** The server reads the Parquet files directly (`ANALOGUES_DATA=/data/app/pretreatment_data`). At every
boot, the machine runs `/usr/local/bin/api-sync-data`: it waits for the `_READY` marker written by `publish.sh`,
then copies only what changed from the bucket. The `.duckdb` files of `pretreatment_data/` are not used.

**Boot** (`aws/user_data.sh.tftpl`, `gcp/startup.sh.tftpl`): Docker, fixed IP (AWS), data disk (formatted if
empty), swap (AWS), data sync, server container and Caddy, health check (AWS).

## Commands

Prerequisites: AWS CLI, `gcloud auth login`, Terraform ≥ 1.10, Docker. From `server/deploy/` (Git Bash). For
Google Cloud, Terraform reads gcloud's token:

```bash
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)   # valid 1 h
```

| Need | Command |
|---|---|
| First deployment | `terraform -chdir=aws apply`, then `./publish.sh aws` (same with `gcp`) |
| New version of the code | `./publish.sh aws image` (build, push, replace the machine); `gcp`, or `both` |
| New data | `./publish.sh aws data` (upload, then the machine resyncs and restarts the API) |
| Infrastructure change | `terraform -chdir=aws plan`, then `apply` |
| Stop without destroying (AWS) | `aws autoscaling update-auto-scaling-group --auto-scaling-group-name <name> --desired-capacity 0` (1 to restart) |
| Stop without destroying (GCP) | `gcloud compute instance-groups managed resize <name> --size 0 --zone <zone>` |
| Shell on the machine | AWS: Session Manager (`aws ssm start-session --target <instance>`); GCP: `gcloud compute ssh <vm> --zone <zone> --tunnel-through-iap` |
| Destroy everything | `terraform -chdir=aws destroy` (also empties the bucket and ECR); GCP: the data disk (`delete_rule = NEVER`) stays, delete it by hand |

The AWS image is built for `linux/arm64` (output `docker_platform`), by emulation on an x86 PC: slower to build.
Back to x86: `-var instance_type=t3.small`.

## Monitoring and logs

- **AWS logs**: CloudWatch `/<name>`, 7 days, one stream per machine and source: `<instance>/startup`,
  `<instance>/server`, `<instance>/caddy`, `<instance>/health`.
  `MSYS_NO_PATHCONV=1 aws logs tail /<name> --follow` (`MSYS_NO_PATHCONV=1`: otherwise Git Bash turns the name
  into a Windows path). Startup log on the machine: `/var/log/api-startup.log`.
- **AWS health**: every 2 min, the machine queries `/api/health` and publishes `AstroWrap/ApiHealth` (1 = ready).
  8 failures in a row (~16 min): the container is restarted; 15 (~30 min): the machine reports itself unhealthy and
  the group replaces it. Alarm `<name>-api-down` → email (SNS: confirm the subscription email once).
- **AWS budget** `<name>-monthly`: email when the actual or forecast spend goes over `budget_usd` (after credits).
- **GCP logs** (Cloud Logging): startup script (`google_metadata_script_runner`), containers
  (`gcplogs-docker-driver`):
  `gcloud logging read 'logName:"gcplogs-docker-driver"' --freshness 1h --format "value(jsonPayload.container.name,jsonPayload.data)"`.
- **GCP auto-healing**: the VM is recreated if `/api/health` does not answer "ready" 10 times in a row (every 90 s),
  20 min after its boot. **Uptime check** every 5 min from 3 regions, email if it fails for ~10 min.
- **GCP budget**: one email at each step of `budget_step` spent in the month, counted **before** the trial credits.
  Needs the *Billing Account Costs Manager* role on the billing account, then `billing_account` in tfvars.

## Costs (approximate)

| | Machine | Disks, IP, storage | Total per month |
|---|---|---|---|
| AWS t4g.small, ca-central-1 | 13.4 USD | ~5.3 USD | ~18.7 USD |
| GCP e2-standard-2, Montreal | ~75.6 CAD | ~8.5 CAD | ~84 CAD |

Outbound traffic: 100 GB/month free on AWS; a search returns ~0.45 MB compressed. The real limit is the CPU.

## Known limits

- **AWS CPU**: in "standard" credit mode (never any overage), a t4g.small without credits runs at 20 % of each core,
  and every machine replacement resets the credits: avoid useless replacements.
- **Downtime at each update**: one machine and one data disk per cloud (the old machine leaves before the new one
  attaches the disk): a few minutes without service.
- **One zone** per cloud: the data disk only exists there.
- **Nominatim** (place names): its policy asks for a server of one's own for heavy public traffic.

## Interface (Cloudflare)

Static files of `ui/`, no compilation. `npm run site` prepares `dist/` (the site without `node_modules`, plus the
library files the pages load). Online, the pages call `https://api.astrowrap.earth`; locally (localhost,
127.0.0.1, `file://`), `http://127.0.0.1:8000`; `?api=https://other` always wins.

```bash
cd ui
npm install                  # once
npm run site                 # -> dist/
npx wrangler login           # once, in the browser
npx wrangler deploy          # configuration: wrangler.jsonc
```

## Files

| File | Role |
|---|---|
| `../Dockerfile`, `../.dockerignore` | server image (python 3.12-slim, libexpat1 for GDAL) |
| `publish.sh` | upload of the image and the data (AWS, Google Cloud or both) |
| `aws/main.tf` | ECR, S3, EBS disk, elastic IP, network, IAM, launch template, Auto Scaling group |
| `aws/monitoring.tf` | logs, alarm, SNS, budget |
| `aws/user_data.sh.tftpl` | boot of the machine |
| `gcp/main.tf` | project APIs, Artifact Registry, GCS, IP, firewall, service account, template, managed group |
| `gcp/monitoring.tf` | uptime check, alert, budget in steps |
| `gcp/startup.sh.tftpl` | boot of the VM |
