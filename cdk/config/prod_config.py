"""Production environment configuration."""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class ProdConfig:
    """Configuration for production environment."""

    environment: str = "prod"
    project: str = "nat-alternative"
    az_count: int = 3
    vpc_cidr: str = "10.1.0.0/16"
    allowed_ssh_cidrs: Optional[List[str]] = None
    nat_instance_type: str = "t3.small"
    nat_root_volume_size: int = 20
    enable_probes: bool = True
    probe_instance_type: str = "t3.nano"
    flow_log_retention_days: int = 30
    app_log_retention_days: int = 14
    logs_kms_key_arn: str = (
        ""  # Use existing key ARN to reuse across deployments (recommended for demos)
    )
    logs_kms_key_alias: str = (
        "alias/nat-alternative-logs"  # Or use alias (recommended - create key once, reuse always)
    )
    app_logs_kms_key_arn: str = ""
    app_logs_kms_key_alias: str = ""
    aws_region: str = "eu-central-1"
    tags: Optional[Dict[str, str]] = None

    def __post_init__(self):
        """Initialize default values for mutable types."""
        if self.allowed_ssh_cidrs is None:
            self.allowed_ssh_cidrs = []
        if self.tags is None:
            self.tags = {"Owner": "network-team", "Environment": "prod"}

    @property
    def prefix(self) -> str:
        """Get resource name prefix."""
        return f"{self.project}-{self.environment}"
