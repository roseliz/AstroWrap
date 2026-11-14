# Worldwide EMIT processing of the mineralogie_terre module on AWS, region us-west-2.
# Spot machines in an Auto Scaling group (capacity 0 to var.machines): if AWS reclaims a machine, the group starts
# another one, which skips the granules already written to the bucket. A machine that has finished its list leaves
# the group; the one that finds everything done sets the capacity to 0. Shutdown = termination. No NAT, no inbound
# access, Earthdata credentials in SSM.

data "aws_caller_identity" "current" {}

locals {
  name    = "mineralogie-terre"
  group   = "mineralogie-terre-${var.run_name}"
  scripts = "${path.module}/../scripts"
}

# ------------------------------------------------------------------ results bucket
resource "aws_s3_bucket" "results" {
  bucket_prefix = "${local.name}-"
  force_destroy = true # terraform destroy empties the bucket (copy the results first)
}

resource "aws_s3_bucket_public_access_block" "results" {
  bucket                  = aws_s3_bucket.results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "results" {
  bucket = aws_s3_bucket.results.id
  rule {
    id     = "delete-after-14-days" # safety net if the bucket is forgotten
    status = "Enabled"
    filter {}
    expiration {
      days = 14
    }
  }
}

# Module scripts and granule list, uploaded to the bucket by Terraform
data "archive_file" "scripts" {
  type        = "zip"
  source_dir  = local.scripts
  output_path = "${path.module}/.build/scripts.zip"
  excludes    = ["**/__pycache__/**", "**/*.pyc"]
}

resource "aws_s3_object" "scripts" {
  bucket = aws_s3_bucket.results.id
  key    = "code/scripts.zip"
  source = data.archive_file.scripts.output_path
  etag   = data.archive_file.scripts.output_md5
}

resource "aws_s3_object" "granule_list" {
  bucket = aws_s3_bucket.results.id
  key    = "inputs/${var.run_name}/list.parquet"
  source = var.granule_list
  etag   = filemd5(var.granule_list)
}

# ------------------------------------------------------------------ live logs (CloudWatch Logs)
resource "aws_cloudwatch_log_group" "logs" {
  name              = "/mineralogie_terre"
  retention_in_days = 7 # a few MB, within the free quota; deleted by terraform destroy
}

# ------------------------------------------------------------------ machine permissions (minimal)
resource "aws_iam_role" "machine" {
  name_prefix = "${local.name}-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "machine" {
  role = aws_iam_role.machine.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "BucketList", Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.results.arn },
      { Sid = "BucketObjects", Effect = "Allow", Action = ["s3:GetObject", "s3:PutObject"], Resource = "${aws_s3_bucket.results.arn}/*" },
      {
        Sid = "EarthdataCredentials", Effect = "Allow", Action = ["ssm:GetParameters"]
        Resource = [for p in ["username", "password"] :
        "arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}${p}"]
      },
      {
        Sid       = "DecryptSSM", Effect = "Allow", Action = ["kms:Decrypt"], Resource = "*"
        Condition = { StringEquals = { "kms:ViaService" = "ssm.${var.region}.amazonaws.com" } }
      },
      {
        Sid      = "StopOwnGroup", Effect = "Allow"
        Action   = ["autoscaling:UpdateAutoScalingGroup", "autoscaling:TerminateInstanceInAutoScalingGroup"]
        Resource = "arn:aws:autoscaling:${var.region}:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/${local.group}"
      },
      {
        Sid      = "CloudWatchLogs", Effect = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = [aws_cloudwatch_log_group.logs.arn, "${aws_cloudwatch_log_group.logs.arn}:*"]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "machine" {
  name_prefix = "${local.name}-"
  role        = aws_iam_role.machine.name
}

# ------------------------------------------------------------------ network: default VPC, public subnets
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
  filter {
    name   = "default-for-az"
    values = ["true"]
  }
}

resource "aws_security_group" "machine" {
  name_prefix = "${local.name}-"
  description = "No inbound access; outbound to the Internet (Earthdata, S3, PyPI, GitHub)"
  vpc_id      = data.aws_vpc.default.id
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# ------------------------------------------------------------------ machine
data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

resource "aws_launch_template" "machine" {
  name_prefix                          = "${local.name}-"
  image_id                             = data.aws_ssm_parameter.ami.value
  instance_initiated_shutdown_behavior = "terminate"
  update_default_version               = true
  iam_instance_profile {
    arn = aws_iam_instance_profile.machine.arn
  }
  network_interfaces {
    associate_public_ip_address = true
    security_groups             = [aws_security_group.machine.id]
    delete_on_termination       = true
  }
  metadata_options {
    http_tokens = "required" # IMDSv2
  }
  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 30
      volume_type           = "gp3"
      delete_on_termination = true
      encrypted             = true
    }
  }
  user_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    region      = var.region
    bucket      = aws_s3_bucket.results.id
    run_name    = var.run_name
    group       = local.group
    ssm_prefix  = var.ssm_prefix
    log_group   = aws_cloudwatch_log_group.logs.name
    parallel    = var.parallel
    max_hours   = var.max_hours
    max_starts  = var.max_starts
    scripts_md5 = data.archive_file.scripts.output_md5
  }))
  tag_specifications {
    resource_type = "instance"
    tags          = { Name = local.group, project = "mineralogie_terre" }
  }
  tag_specifications {
    resource_type = "volume"
    tags          = { project = "mineralogie_terre" }
  }
}

resource "aws_autoscaling_group" "machine" {
  name                      = local.group
  min_size                  = 0
  max_size                  = var.machines
  desired_capacity          = var.start ? var.machines : 0
  vpc_zone_identifier       = data.aws_subnets.default.ids
  health_check_type         = "EC2"
  health_check_grace_period = 300
  wait_for_capacity_timeout = "0" # do not wait for the machine during terraform apply

  mixed_instances_policy {
    instances_distribution {
      on_demand_base_capacity                  = 0
      on_demand_percentage_above_base_capacity = var.spot ? 0 : 100
      spot_allocation_strategy                 = "price-capacity-optimized"
    }
    launch_template {
      launch_template_specification {
        launch_template_id = aws_launch_template.machine.id
        version            = "$Latest"
      }
      dynamic "override" {
        for_each = var.instance_types
        content {
          instance_type = override.value
        }
      }
    }
  }

  tag {
    key                 = "project"
    value               = "mineralogie_terre"
    propagate_at_launch = true
  }

  depends_on = [aws_iam_role_policy.machine, aws_s3_object.scripts, aws_s3_object.granule_list]
}

# ------------------------------------------------------------------ budget (whole account)
resource "aws_budgets_budget" "cap" {
  name         = "${local.name}-cap-30"
  budget_type  = "COST"
  limit_amount = "30"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Without this, spending covered by credits shows as $0 and the alerts are never sent
  cost_types {
    include_credit = false
    include_refund = false
  }

  dynamic "notification" {
    for_each = [10, 20, 30]
    content {
      comparison_operator        = "GREATER_THAN"
      threshold                  = notification.value
      threshold_type             = "ABSOLUTE_VALUE"
      notification_type          = "ACTUAL"
      subscriber_email_addresses = [var.alert_email]
    }
  }
}
