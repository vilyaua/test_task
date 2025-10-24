locals {
  probe_user_data = <<-EOF
    #!/usr/bin/env bash
    set -euo pipefail

    LOG_FILE="/var/log/nat-probe.log"
    exec > >(tee -a "$${LOG_FILE}") 2>&1

    echo "$(date --iso-8601=seconds) [INFO] Starting NAT connectivity probe"

    # Ensure the SSM agent is available for log collection
    systemctl enable --now amazon-ssm-agent

    # Install minimal tooling for outbound checks
    dnf install -y curl bind-utils traceroute >/dev/null
    curl -fsSL https://s3.amazonaws.com/amazoncloudwatch-agent/amazon_linux/amd64/latest/amazon-cloudwatch-agent.rpm -o /tmp/amazon-cloudwatch-agent.rpm
    rpm -Uvh /tmp/amazon-cloudwatch-agent.rpm >/dev/null

    CW_LOG_GROUP_PROBE="${aws_cloudwatch_log_group.probes.name}"
    cat >/opt/aws/amazon-cloudwatch-agent/etc/amazon-cloudwatch-agent.json <<CONFIG
    {
      "logs": {
        "logs_collected": {
          "files": {
            "collect_list": [
              {
                "file_path": "/var/log/nat-probe.log",
                "log_group_name": "$${CW_LOG_GROUP_PROBE}",
                "log_stream_name": "probe-{instance_id}",
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

    endpoints=(
      "https://checkip.amazonaws.com"
      "https://aws.amazon.com"
    )

    for endpoint in "$${endpoints[@]}"; do
      if curl --silent --show-error --max-time 10 "$${endpoint}" >/tmp/probe.out; then
        echo "$(date --iso-8601=seconds) [INFO] curl $${endpoint} succeeded: $(head -n 1 /tmp/probe.out)"
      else
        echo "$(date --iso-8601=seconds) [ERROR] curl $${endpoint} failed"
        exit 2
      fi
    done

    if dig +short cloudfront.net >/tmp/dns.out; then
      echo "$(date --iso-8601=seconds) [INFO] DNS lookup succeeded: $(head -n 1 /tmp/dns.out)"
    else
      echo "$(date --iso-8601=seconds) [ERROR] DNS lookup failed"
      exit 3
    fi

    echo "$(date --iso-8601=seconds) [INFO] Traceroute sample to 1.1.1.1"
    traceroute -w 2 -q 1 1.1.1.1 | head -n 10

    echo "$(date --iso-8601=seconds) [INFO] NAT connectivity probe completed successfully; entering standby for health monitoring"

    # Keep instance online for subsequent health checks and log collection.
    while true; do
      echo "$(date --iso-8601=seconds) [INFO] Heartbeat: probe instance idle" >>"$${LOG_FILE}"
      sleep 5
    done
  EOF
}

resource "aws_security_group" "probe" {
  count = var.enable_probes ? 1 : 0

  name        = "${local.prefix}-probe-sg"
  description = "Allows outbound traffic for NAT connectivity probe instances"
  vpc_id      = aws_vpc.this.id

  # tfsec:ignore:aws-ec2-no-public-egress-sgr Probe instances require full egress to validate NAT connectivity.
  egress {
    description = "Probe outbound to internet"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-probe-sg"
    Role = "probe"
  })
}

resource "aws_instance" "probe" {
  for_each = var.enable_probes ? aws_subnet.private : {}

  ami           = data.aws_ssm_parameter.al2023_ami.value
  instance_type = var.probe_instance_type
  subnet_id     = each.value.id

  associate_public_ip_address          = false
  vpc_security_group_ids               = [aws_security_group.probe[0].id]
  user_data                            = local.probe_user_data
  user_data_replace_on_change          = true
  instance_initiated_shutdown_behavior = "terminate"
  monitoring                           = false
  iam_instance_profile                 = aws_iam_instance_profile.instance.name

  metadata_options {
    http_endpoint          = "enabled"
    http_tokens            = "required"
    instance_metadata_tags = "enabled"
  }

  root_block_device {
    volume_size = 8
    volume_type = "gp3"
    encrypted   = true
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-probe-${each.key}"
    Role = "probe"
  })

  depends_on = [
    aws_route.private_default
  ]
}
