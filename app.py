#!/usr/bin/env python3
"""CDK app entry point for NAT Gateway Alternative."""
import os

import aws_cdk as cdk

from cdk.config.prod_config import ProdConfig
from cdk.config.test_config import TestConfig
from cdk.infra.nat_stack import NatAlternativeStack

app = cdk.App()

# Determine environment from context or environment variable
env_name = app.node.try_get_context("environment") or os.getenv("CDK_ENVIRONMENT", "test")

# Load configuration based on environment
if env_name == "prod":
    config = ProdConfig()
else:
    config = TestConfig()

# Create stack
stack = NatAlternativeStack(
    app,
    f"NatAlternative{env_name.capitalize()}",
    config=config,
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=config.aws_region,
    ),
)

# Add tags to all resources
for key, value in config.tags.items():
    cdk.Tags.of(stack).add(key, value)

app.synth()

