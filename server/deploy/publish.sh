#!/usr/bin/env bash
# ./publish.sh [aws|gcp|both] [all|image|data]
set -euo pipefail
cd "$(dirname "$0")"
TARGET=${1:-both}
WHAT=${2:-all}
DATA=../../pretreatment_data
case "$TARGET" in aws|gcp|both) ;; *) echo "unknown cloud: $TARGET (aws, gcp or both)" >&2; exit 2 ;; esac
case "$WHAT" in all|image|data) ;; *) echo "unknown: $WHAT (all, image or data)" >&2; exit 2 ;; esac

# AWS
aws_publish() {
  local TF="terraform -chdir=aws"
  local ECR REGION BUCKET GROUP PLATFORM INSTANCE
  ECR=$($TF output -raw ecr)
  REGION=$(echo "$ECR" | cut -d. -f4)
  BUCKET=$($TF output -raw bucket)
  GROUP=$($TF output -raw group)
  PLATFORM=$($TF output -raw docker_platform 2>/dev/null || echo linux/amd64)

  if [ "$WHAT" != data ]; then
    aws ecr get-login-password --region "$REGION" | docker login --username AWS --password-stdin "${ECR%%/*}"
    docker buildx build --platform "$PLATFORM" -t "$ECR:latest" --push ..
  fi
  if [ "$WHAT" != image ]; then
    aws s3 sync "$DATA" "s3://$BUCKET/pretreatment_data" --region "$REGION" \
      --exclude "*" --include "*.parquet" --delete
    echo ok | aws s3 cp - "s3://$BUCKET/pretreatment_data/_READY" --region "$REGION"
  fi
  INSTANCE=$(aws autoscaling describe-auto-scaling-groups --auto-scaling-group-names "$GROUP" --region "$REGION" \
    --query "AutoScalingGroups[0].Instances[?LifecycleState=='InService'].InstanceId | [0]" --output text)
  if [ "$WHAT" = data ] && [ "$INSTANCE" != None ]; then
    aws ssm send-command --region "$REGION" --instance-ids "$INSTANCE" --document-name AWS-RunShellScript \
      --parameters 'commands=["/usr/local/bin/api-sync-data && docker restart server"]' \
      --query Command.CommandId --output text
  elif [ "$WHAT" != data ]; then
    aws autoscaling start-instance-refresh --auto-scaling-group-name "$GROUP" --region "$REGION" \
      --preferences MinHealthyPercentage=0
  fi
}

# Google Cloud
gcp_publish() {
  local TF="terraform -chdir=gcp"
  local IMAGE BUCKET GROUP ZONE PLATFORM INSTANCE READY
  GOOGLE_OAUTH_ACCESS_TOKEN=${GOOGLE_OAUTH_ACCESS_TOKEN:-$(gcloud auth print-access-token)}
  export GOOGLE_OAUTH_ACCESS_TOKEN
  IMAGE=$($TF output -raw image)
  BUCKET=$($TF output -raw bucket)
  GROUP=$($TF output -raw group)
  ZONE=$($TF output -raw zone)
  PLATFORM=$($TF output -raw docker_platform)

  if [ "$WHAT" != data ]; then
    gcloud auth print-access-token | docker login -u oauth2accesstoken --password-stdin "https://${IMAGE%%/*}"
    docker buildx build --platform "$PLATFORM" -t "$IMAGE" --push ..
  fi
  if [ "$WHAT" != image ]; then
    gcloud storage rsync "$DATA" "gs://$BUCKET/pretreatment_data" --recursive \
      --delete-unmatched-destination-objects --exclude '^(?!.*\.parquet$).*'
    READY=$(mktemp)  # stdin fails on Windows
    echo ok > "$READY"
    gcloud storage cp "$READY" "gs://$BUCKET/pretreatment_data/_READY"
    rm -f "$READY"
  fi
  INSTANCE=$(gcloud compute instance-groups managed list-instances "$GROUP" --zone "$ZONE" \
    --format "value(instance.basename())" --limit 1)
  if [ "$WHAT" = data ] && [ -n "$INSTANCE" ]; then
    gcloud compute ssh "$INSTANCE" --zone "$ZONE" --tunnel-through-iap --quiet \
      --command "sudo /usr/local/bin/api-sync-data && sudo docker restart server"
  elif [ "$WHAT" != data ]; then
    gcloud compute instance-groups managed rolling-action replace "$GROUP" --zone "$ZONE" \
      --replacement-method recreate --max-surge 0 --max-unavailable 1
  fi
}

if [ "$TARGET" = aws ] || [ "$TARGET" = both ]; then aws_publish; fi
if [ "$TARGET" = gcp ] || [ "$TARGET" = both ]; then gcp_publish; fi
