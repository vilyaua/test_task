# Test Environment Deployment

Follow these steps to provision the test environment using the Terraform configuration under `infra/`.

1. **Select credentials**  
   The provider defaults to the `terraform` shared-credentials profile. Export `AWS_PROFILE=terraform` if you rely on environment variables, or pass `-var 'aws_profile=<profile>'` to override.

2. **Initialize Terraform**  
   From the `infra/` directory, download providers and set up the local state:
   ```bash
   terraform init
   ```

3. **Plan the deployment**  
   Generate a plan against the test environment variable file:
   ```bash
   terraform plan -var-file=environments/test/vars.tfvars
   ```

4. **Apply changes**  
   Review the plan, then apply to create the VPC, subnets, NAT instances, and associated routing:
   ```bash
   terraform apply -var-file=environments/test/vars.tfvars
   ```

5. **Post-deploy checks**  
   - Confirm the NAT instances are running in the public subnets and have Elastic IPs.  
   - Verify private route tables point `0.0.0.0/0` to the NAT instance in the same AZ.  
   - Probe instances (`t3.nano`) in private subnets run automatic connectivity tests and self-terminate; inspect `/var/log/nat-probe.log` via the console if needed.
   - Use `aws ec2 describe-route-tables` and `aws ec2 describe-instances` if you need CLI confirmation.
   - Reference `docs/test-environment.mmd` for a Mermaid diagram of the expected topology.

6. **Destroy when finished**  
   Tear down the test environment after validation to avoid ongoing costs:
   ```bash
   terraform destroy -var-file=environments/test/vars.tfvars
   ```
