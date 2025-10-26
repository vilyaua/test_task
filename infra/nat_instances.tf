locals {
  nat_user_data = <<-EOF
    #!/usr/bin/env bash
    set -euxo pipefail

    # Enable IPv4 forwarding persistently
    cat <<'EOT' >/etc/sysctl.d/98-nat.conf
    net.ipv4.ip_forward = 1
    net.ipv4.conf.all.rp_filter = 0
    net.ipv4.conf.default.rp_filter = 0
    EOT
    sysctl -p /etc/sysctl.d/98-nat.conf

    # Install iptables tooling; AL2023 already ships with curl
    dnf install -y iptables-nft iptables-services
    systemctl enable iptables

    curl -fsSL https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm -o /tmp/amazon-cloudwatch-agent.rpm
    rpm -Uvh /tmp/amazon-cloudwatch-agent.rpm

    CW_LOG_GROUP_NAT="${aws_cloudwatch_log_group.nat_instances.name}"
    cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<CONFIG
    {
      "logs": {
        "logs_collected": {
          "files": {
            "collect_list": [
              {
                "file_path": "/var/log/cloud-init-output.log",
                "log_group_name": "$${CW_LOG_GROUP_NAT}",
                "log_stream_name": "nat-{instance_id}",
                "timestamp_format": "%Y-%m-%dT%H:%M:%S"
              }
            ]
          }
        }
      }
    }
    CONFIG

    /opt/aws/amazon-cloudwatch-agent/bin/amazon-cloudwatch-agent-ctl -a fetch-config -m ec2 -c file:/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json -s
    systemctl enable --now amazon-cloudwatch-agent

    # Ensure the filter table allows forwarding for traffic traversing the instance
    iptables -F FORWARD
    iptables -P FORWARD ACCEPT

    # Flush existing NAT rules and configure masquerading on the detected default interface
    primary_iface=$(ip route show default | awk 'NR==1 {print $5}')
    : "$${primary_iface:=ens5}"
    iptables -t nat -F
    iptables -t nat -A POSTROUTING -o "$${primary_iface}" -j MASQUERADE

    # Persist iptables configuration and reload the service to pick up changes
    iptables-save >/etc/sysconfig/iptables
    systemctl restart iptables

    # Ensure the SSM agent is online for automation
    systemctl enable --now amazon-ssm-agent

    # Harden SSH if it gets enabled later
    sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
    systemctl restart sshd
  EOF
}

resource "aws_security_group" "nat" {
  name        = "${local.prefix}-nat-sg"
  description = "Controls access to NAT instances"
  vpc_id      = aws_vpc.this.id

  ingress {
    description = "Allow traffic from private subnets"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = values(local.private_subnet_cidrs)
  }

  dynamic "ingress" {
    for_each = var.allowed_ssh_cidrs
    content {
      description = "Admin SSH"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = [ingress.value]
    }
  }

  # tfsec:ignore:aws-ec2-no-public-egress-sgr NAT instances require 0.0.0.0/0 egress to serve private subnets.
  # tfsec:ignore:aws-ec2-add-description-to-security-group-rule Description provided; tfsec rule misfires on inline blocks.
  egress {
    description = "Allow outbound internet access"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-sg"
    Tier = "edge"
  })
}

resource "aws_launch_template" "nat" {
  for_each = local.public_subnet_cidrs

  name_prefix   = "${local.prefix}-nat-${replace(each.key, "-", "")}-"
  image_id      = data.aws_ssm_parameter.al2023_ami.value
  instance_type = var.nat_instance_type

  iam_instance_profile {
    name = aws_iam_instance_profile.instance.name
  }

  metadata_options {
    http_endpoint          = "enabled"
    http_tokens            = "required"
    instance_metadata_tags = "enabled"
  }

  monitoring {
    enabled = false
  }

  network_interfaces {
    associate_public_ip_address = true
    delete_on_termination       = true
    device_index                = 0
    subnet_id                   = aws_subnet.public[each.key].id
    security_groups             = [aws_security_group.nat.id]
  }

  user_data = base64encode(local.nat_user_data)

  block_device_mappings {
    device_name = "/dev/xvda"
    ebs {
      volume_size           = var.nat_root_volume_size
      volume_type           = "gp3"
      encrypted             = true
      delete_on_termination = true
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = merge(local.base_tags, {
      Name = "${local.prefix}-nat-${each.key}"
      Role = "nat"
    })
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_autoscaling_group" "nat" {
  for_each = local.public_subnet_cidrs

  name                      = "${local.prefix}-nat-${replace(each.key, "-", "")}"
  max_size                  = 1
  min_size                  = 1
  desired_capacity          = 1
  health_check_type         = "EC2"
  health_check_grace_period = 60
  vpc_zone_identifier       = [aws_subnet.public[each.key].id]

  launch_template {
    id      = aws_launch_template.nat[each.key].id
    version = "$Latest"
  }

  tag {
    key                 = "Name"
    value               = "${local.prefix}-nat-${each.key}"
    propagate_at_launch = true
  }

  tag {
    key                 = "Project"
    value               = var.project
    propagate_at_launch = true
  }

  tag {
    key                 = "Environment"
    value               = var.environment
    propagate_at_launch = true
  }

  tag {
    key                 = "Role"
    value               = "nat"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [aws_iam_instance_profile.instance]
}

resource "aws_eip" "nat" {
  for_each = local.public_subnet_cidrs

  domain = "vpc"

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-eip-${each.key}"
  })
}
