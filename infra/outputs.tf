output "vpc_id" {
  description = "Identifier for the NAT alternative VPC."
  value       = aws_vpc.this.id
}

output "public_subnet_ids" {
  description = "Public subnet identifiers keyed by AZ."
  value       = { for az, subnet in aws_subnet.public : az => subnet.id }
}

output "private_subnet_ids" {
  description = "Private subnet identifiers keyed by AZ."
  value       = { for az, subnet in aws_subnet.private : az => subnet.id }
}

output "nat_instance_ids" {
  description = "NAT instance identifiers keyed by AZ."
  value       = { for az, instance in aws_instance.nat : az => instance.id }
}

output "nat_eip_addresses" {
  description = "Elastic IPs allocated to NAT instances."
  value       = { for az, eip in aws_eip.nat : az => eip.public_ip }
}
