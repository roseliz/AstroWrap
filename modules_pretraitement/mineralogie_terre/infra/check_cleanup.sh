#!/usr/bin/env bash
# After terraform destroy: check that nothing active or billable is left in us-west-2 (read only).
export MSYS_NO_PATHCONV=1   # Git Bash (Windows): do not convert /mineralogie_terre/ into a file path
set -uo pipefail
R=us-west-2
echo "Instances (not terminated):"
aws ec2 describe-instances --region $R --filters Name=tag:project,Values=mineralogie_terre \
  Name=instance-state-name,Values=pending,running,stopping,stopped \
  --query "Reservations[].Instances[].[InstanceId,State.Name,InstanceType]" --output text
echo "Volumes:"
aws ec2 describe-volumes --region $R --filters Name=tag:project,Values=mineralogie_terre --query "Volumes[].[VolumeId,State,Size]" --output text
echo "Open Spot requests:"
aws ec2 describe-spot-instance-requests --region $R --filters Name=state,Values=open,active --query "SpotInstanceRequests[].[SpotInstanceRequestId,State]" --output text
echo "Auto Scaling groups:"
aws autoscaling describe-auto-scaling-groups --region $R --query "AutoScalingGroups[?starts_with(AutoScalingGroupName,'mineralogie-terre')].[AutoScalingGroupName,DesiredCapacity]" --output text
echo "S3 buckets:"
aws s3api list-buckets --query "Buckets[?starts_with(Name,'mineralogie-terre')].Name" --output text
echo "Elastic IP addresses:"
aws ec2 describe-addresses --region $R --query "Addresses[].PublicIp" --output text
echo "NAT gateways:"
aws ec2 describe-nat-gateways --region $R --filter Name=state,Values=pending,available --query "NatGateways[].NatGatewayId" --output text
echo "SSM parameters of the project:"
aws ssm describe-parameters --region $R --parameter-filters Key=Name,Option=BeginsWith,Values=/mineralogie_terre/ --query "Parameters[].Name" --output text
echo "(empty lists = nothing is left)"
