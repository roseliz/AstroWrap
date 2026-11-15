# Deploy

Same server image on AWS (`aws/`) and Google Cloud (`gcp/`), two independent Terraform folders. The UI is on Cloudflare.

| | URL |
|---|---|
| Site | https://astrowrap.earth |
| API (AWS) | https://api.astrowrap.earth/api/health |
| API (GCP) | https://api-gcp.astrowrap.earth/api/health |

## Setup

Each folder needs two private files (git-ignored):

- `backend.hcl`: state bucket, see `backend.hcl.example`
- `terraform.tfvars`: `name`, `alert_email`, and for GCP `project`, `billing_account`, `data_device_name`

```bash
terraform -chdir=aws init -backend-config=backend.hcl
export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token)
terraform -chdir=gcp init -backend-config=backend.hcl
```

Requires AWS CLI, gcloud, Terraform >= 1.10 and Docker.

## Commands

Run from `server/deploy/`:

| | |
|---|---|
| New code | `./publish.sh both image` |
| New data | `./publish.sh both data` |
| Infra change | `terraform -chdir=aws plan`, then `apply` |
| Stop AWS | `aws autoscaling update-auto-scaling-group --auto-scaling-group-name <name> --desired-capacity 0` |
| Stop GCP | `gcloud compute instance-groups managed resize <name> --size 0 --zone <zone>` |
| Shell | AWS: `aws ssm start-session --target <instance>`; GCP: `gcloud compute ssh <vm> --zone <zone> --tunnel-through-iap` |

Replace `both` with `aws` or `gcp` for one cloud.

## How it works

One machine per cloud, behind Caddy (HTTPS). Data lives on a disk that survives machine replacement. At boot the machine syncs the Parquet files from S3/GCS to `/data/app/pretreatment_data`, then starts the server.

DNS (Cloudflare): `api` and `api-gcp` are A records to `terraform output ip`, DNS only.

## UI

```bash
cd ui
npm install
npm run site
npx wrangler deploy
```

## Logs

- AWS: CloudWatch `/<name>` (`MSYS_NO_PATHCONV=1 aws logs tail /<name> --follow`)
- GCP: Cloud Logging, `gcplogs-docker-driver`
