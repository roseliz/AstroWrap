data "aws_caller_identity" "current" {}

locals {
  sslip             = "${replace(aws_eip.server.public_ip, ".", "-")}.sslip.io"
  domain            = var.domain != "" ? var.domain : local.sslip
  caddy_domains     = join(", ", distinct([local.domain, local.sslip]))
  metrics_namespace = "AstroWrap"
  health_period_s   = 120
}

# Image and data
resource "aws_ecr_repository" "server" {
  name                 = var.name
  image_tag_mutability = "MUTABLE"
  force_delete         = true
}

resource "aws_ecr_lifecycle_policy" "server" {
  repository = aws_ecr_repository.server.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1, description = "keep 2 images of ~210 MB (free plan: 500 MB)"
      selection    = { tagStatus = "any", countType = "imageCountMoreThan", countNumber = 2 }
      action       = { type = "expire" }
    }]
  })
}

resource "aws_s3_bucket" "data" {
  bucket_prefix = "${var.name}-"
  force_destroy = true
}

resource "aws_s3_bucket_public_access_block" "data" {
  bucket                  = aws_s3_bucket.data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Disk and IP
resource "aws_ebs_volume" "data" {
  availability_zone = var.zone
  size              = var.data_disk_gb
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${var.name}-data" }
}

resource "aws_eip" "server" {
  domain = "vpc"
  tags   = { Name = var.name }
}

# Network
data "aws_vpc" "default" {
  default = true
}

data "aws_subnet" "zone" {
  vpc_id            = data.aws_vpc.default.id
  availability_zone = var.zone
  default_for_az    = true
}

resource "aws_security_group" "server" {
  name_prefix = "${var.name}-"
  description = "Inbound HTTP and HTTPS; outbound to the Internet"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "HTTP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
  lifecycle {
    create_before_destroy = true
    ignore_changes        = [description] # immutable
  }
}

# Machine permissions
resource "aws_iam_role" "machine" {
  name_prefix = "${var.name}-"
  assume_role_policy = jsonencode({
    Version   = "2012-10-17"
    Statement = [{ Effect = "Allow", Principal = { Service = "ec2.amazonaws.com" }, Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy_attachment" "ssm" {
  role       = aws_iam_role.machine.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_role_policy_attachment" "ecr" {
  role       = aws_iam_role.machine.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryReadOnly"
}

resource "aws_iam_role_policy" "machine" {
  role = aws_iam_role.machine.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Sid = "BucketList", Effect = "Allow", Action = ["s3:ListBucket"], Resource = aws_s3_bucket.data.arn },
      { Sid = "BucketRead", Effect = "Allow", Action = ["s3:GetObject"], Resource = "${aws_s3_bucket.data.arn}/*" },
      { Sid = "Describe", Effect = "Allow", Action = ["ec2:DescribeVolumes", "ec2:DescribeAddresses"], Resource = "*" },
      {
        Sid = "AttachDisk", Effect = "Allow", Action = ["ec2:AttachVolume"]
        Resource = [aws_ebs_volume.data.arn,
        "arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]
      },
      { Sid = "AssociateIP", Effect = "Allow", Action = ["ec2:AssociateAddress"], Resource = "*" },
      {
        Sid       = "HealthMetric", Effect = "Allow", Action = ["cloudwatch:PutMetricData"], Resource = "*"
        Condition = { StringEquals = { "cloudwatch:namespace" = local.metrics_namespace } }
      },
      {
        Sid      = "ReportUnhealthy", Effect = "Allow", Action = ["autoscaling:SetInstanceHealth"]
        Resource = "arn:aws:autoscaling:${var.region}:${data.aws_caller_identity.current.account_id}:autoScalingGroup:*:autoScalingGroupName/${var.name}"
      },
      {
        Sid      = "Logs", Effect = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
        Resource = [aws_cloudwatch_log_group.logs.arn, "${aws_cloudwatch_log_group.logs.arn}:*"]
      },
    ]
  })
}

resource "aws_iam_instance_profile" "machine" {
  name_prefix = "${var.name}-"
  role        = aws_iam_role.machine.name
}

# Machine
data "aws_ec2_instance_type" "machine" {
  instance_type = var.instance_type
}

locals {
  architecture = contains(data.aws_ec2_instance_type.machine.supported_architectures, "arm64") ? "arm64" : "x86_64"
}

data "aws_ssm_parameter" "ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-${local.architecture}"
}

resource "aws_launch_template" "server" {
  name_prefix            = "${var.name}-"
  image_id               = data.aws_ssm_parameter.ami.value
  instance_type          = var.instance_type
  update_default_version = true
  vpc_security_group_ids = [aws_security_group.server.id]

  iam_instance_profile {
    arn = aws_iam_instance_profile.machine.arn
  }

  # No CPU overage
  credit_specification {
    cpu_credits = "standard"
  }

  metadata_options {
    http_tokens                 = "required"
    http_put_response_hop_limit = 2
  }

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = 8
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  user_data = base64encode(templatefile("${path.module}/user_data.sh.tftpl", {
    region    = var.region
    volume    = aws_ebs_volume.data.id
    eip       = aws_eip.server.allocation_id
    bucket    = aws_s3_bucket.data.id
    registry  = split("/", aws_ecr_repository.server.repository_url)[0]
    image     = "${aws_ecr_repository.server.repository_url}:${var.image_tag}"
    domains   = local.caddy_domains
    cors      = var.cors
    group     = var.name
    namespace = local.metrics_namespace
    period    = local.health_period_s
    log_group = aws_cloudwatch_log_group.logs.name
  }))

  tag_specifications {
    resource_type = "instance"
    tags          = { Name = var.name }
  }
}

resource "aws_autoscaling_group" "server" {
  name                = var.name
  min_size            = 0
  max_size            = 1
  desired_capacity    = 1
  vpc_zone_identifier = [data.aws_subnet.zone.id]
  health_check_type   = "EC2"

  launch_template {
    id      = aws_launch_template.server.id
    version = aws_launch_template.server.latest_version
  }

  # Single data disk
  instance_refresh {
    strategy = "Rolling"
    preferences {
      min_healthy_percentage = 0
    }
  }

  tag {
    key                 = "project"
    value               = var.name
    propagate_at_launch = true
  }
}
