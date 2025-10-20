variable "project" {
  description = "Project identifier for tagging and resource naming."
  type        = string
  default     = "nat-alternative"
}

variable "environment" {
  description = "Environment label (e.g., test, prod)."
  type        = string
  default     = "test"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "azs" {
  description = "Optional list of AZs to use. Leave empty to auto-select."
  type        = list(string)
  default     = []
}

variable "az_count" {
  description = "Number of AZs to use when azs is not provided."
  type        = number
  default     = 2
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks permitted for SSH to NAT instances."
  type        = list(string)
  default     = []
}

variable "nat_instance_type" {
  description = "EC2 instance type used for NAT instances."
  type        = string
  default     = "t3.small"
}

variable "nat_root_volume_size" {
  description = "Root volume size (GiB) for NAT instances."
  type        = number
  default     = 20
}

variable "tags" {
  description = "Additional tags applied to all resources."
  type        = map(string)
  default     = {}
}

variable "aws_profile" {
  description = "Optional shared credentials profile for local workflows. Leave empty when using OIDC in CI."
  type        = string
  default     = ""
}

variable "aws_region" {
  description = "AWS region targeted by Terraform deployments."
  type        = string
  default     = "eu-central-1"
}

variable "enable_probes" {
  description = "Whether to launch NAT connectivity probe instances in private subnets."
  type        = bool
  default     = true
}

variable "probe_instance_type" {
  description = "Instance type used for connectivity probe instances."
  type        = string
  default     = "t3.nano"
}

variable "flow_log_retention_days" {
  description = "Retention period for VPC flow logs in CloudWatch Logs."
  type        = number
  default     = 30
}

variable "logs_kms_key_arn" {
  description = "Optional existing KMS key ARN for encrypting VPC flow logs. Leave empty to create a dedicated key."
  type        = string
  default     = ""
}

variable "logs_kms_key_alias" {
  description = "Optional existing KMS CMK alias (e.g., alias/nat-kms). Used when ARN is not provided."
  type        = string
  default     = ""
}
