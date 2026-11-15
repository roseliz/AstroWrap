# Worldwide EMIT Processing on AWS

Runs `scripts/batch.py` of `mineralogie_terre` on AWS, in region `us-west-2`. Spot machines (2 vCPU) in an Auto Scaling group read EMIT directly from the NASA buckets and write two small Parquet files per granule to an S3 bucket. If AWS reclaims a machine, the group starts another one, which skips the granules already done. At the end, the machine sets the group to 0 and shuts down.

| Resource | Setting |
| :--- | :--- |
| S3 bucket | `force_destroy`, public access blocked, deleted after 14 days |
| Machine role | read/write on this bucket, read of the 2 SSM parameters, stop of its own group; nothing else |
| Network | default VPC, no inbound access, no NAT |
| Machine | Amazon Linux 2023, Spot `price-capacity-optimized`, shutdown = termination, disk deleted with it |
| Safeguards | stop after `max_hours` (36 h); stop when more than `max_starts` (8) machines started for one run |
| Budget | alerts at $10, $20 and $30 to `alert_email` (credits excluded, otherwise the alerts never fire) |
| Earthdata credentials | SSM SecureString parameters created by `credentials.sh`, outside Terraform |

## Requirements

Terraform ≥ 1.5, the AWS CLI with credentials for the target account, and `.env` at the repository root with `EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD`. The granule list comes from `scripts/selection.py`.

The budget alert address has no default and is never stored in the code. Set it once per shell:

```bash
export TF_VAR_alert_email="you@example.com"
```

## Steps

Run these from `modules_pretraitement/mineralogie_terre/infra/`.

1. Store the Earthdata credentials in SSM (read from `.env`, never printed):

   ```bash
   ./credentials.sh create
   ```

2. Build the pilot list (`lists/pilot.parquet`, 33 granules):

   ```bash
   python make_list.py
   ```

3. Plan and start the pilot. The machine starts, works and shuts down by itself.

   ```bash
   terraform init
   ```

   ```bash
   terraform plan -var "granule_list=lists/pilot.parquet" -var "run_name=pilot" -out pilot.tfplan
   ```

   ```bash
   terraform apply pilot.tfplan
   ```

4. Copy the pilot results:

   ```bash
   aws s3 sync s3://<bucket>/results/pilot ../../../cache/mineralogie_terre/resultats_pilote --region us-west-2
   ```

5. Run the full list (`python make_list.py --full`), with the same plan and `run_name=full` and `granule_list=lists/full.parquet`. Then copy the results to the folder that `merge.py` reads:

   ```bash
   aws s3 sync s3://<bucket>/results/full ../../../cache/mineralogie_terre/resultats --region us-west-2
   ```

6. Destroy everything, delete the credentials, and check that nothing is left:

   ```bash
   terraform destroy -var "granule_list=lists/full.parquet"
   ```

   ```bash
   ./credentials.sh delete && ./check_cleanup.sh
   ```

Monitoring: `s3://<bucket>/logs/<run>/<machine>.log` (every 5 min), `s3://<bucket>/state/<run>/`, and live logs with `aws logs tail /mineralogie_terre --follow`.

Files that Terraform and `make_list.py` generate stay local and are git-ignored: `.terraform/`, state and plan files, `.build/`, `lists/`.
