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

    # Install iptables services to persist NAT rules
    dnf install -y iptables-nft-services
    systemctl enable --now iptables

    # Flush existing NAT rules and configure masquerading
    iptables -t nat -F
    iptables -t nat -A POSTROUTING -o eth0 -j MASQUERADE

    # Persist iptables configuration
    iptables-save >/etc/sysconfig/iptables

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

resource "aws_instance" "nat" {
  for_each = local.public_subnet_cidrs

  ami                         = data.aws_ssm_parameter.al2023_ami.value
  instance_type               = var.nat_instance_type
  subnet_id                   = aws_subnet.public[each.key].id
  associate_public_ip_address = true
  source_dest_check           = false
  vpc_security_group_ids      = [aws_security_group.nat.id]
  user_data                   = local.nat_user_data

  metadata_options {
    http_endpoint          = "enabled"
    http_tokens            = "required"
    instance_metadata_tags = "enabled"
  }

  root_block_device {
    volume_size = var.nat_root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  lifecycle {
    create_before_destroy = true
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-${each.key}"
    Role = "nat"
  })
}

resource "aws_eip" "nat" {
  for_each = aws_instance.nat

  domain   = "vpc"
  instance = each.value.id

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-eip-${each.key}"
  })
}

resource "aws_route" "private_default" {
  for_each = aws_route_table.private

  route_table_id         = each.value.id
  destination_cidr_block = "0.0.0.0/0"
  network_interface_id   = aws_instance.nat[each.key].primary_network_interface_id
}
