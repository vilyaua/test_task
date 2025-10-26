## Next Steps for Demo Automation

1. **Convert NAT EC2s to single-instance ASGs**
   - Introduce a Launch Template encapsulating the current NAT user data, security group, IAM profile, and root volume settings.
   - Create one Auto Scaling Group per AZ (desired = 1, max = 1) targeting the existing public subnets; tag each ASG/instance consistently so the rest of the tooling can find them.
   - Update route-table attachments to reference the NAT ENI created by the ASG instances (may require a Lambda-backed custom resource or lifecycle hook to re-point routes when instances refresh).

2. **Enhance `demo_health` Lambda**
   - Persist each run’s summary (NAT/probe SSM status, log freshness, probe results) to DynamoDB or S3 for dashboard consumption.
   - Publish custom CloudWatch metrics (`NATHealthy`, `ProbeHealthy`, `LogFreshnessMinutes`) so dashboards and alarms can key off structured data instead of ad-hoc parsing.
   - Schedule the Lambda via EventBridge (e.g., every 2 minutes) so health data stays current even without manual invocations.

3. **Design the dashboard**
   - Build a CloudWatch Dashboard (or Grafana board) showing: NAT/probe health metrics per AZ, VPC flow log ingestion, CloudWatch Agent delivery, and recent probe log snippets.
   - Link to the latest DynamoDB/S3 snapshot so demo observers can inspect the JSON payload.

4. **Auto-heal workflow**
   - Create a `nat-auto-heal` Lambda that reacts to CloudWatch Alarms (NATHealthy == 0) and requests an ASG instance refresh or forces `SetDesiredCapacity(1)` to trigger a replacement.
   - Scope its IAM role to `autoscaling`, `ec2:DescribeInstances/ReplaceRoute`, and logging; wire EventBridge rules so alarms invoke the function automatically.

5. **Demo runbook**
   - Document the end-to-end flow: open dashboard, run `demo_health`, terminate a NAT, observe alarms + Lambda action, confirm ASG launches a replacement, show probes/logs recovering.
   - Include cleanup instructions (simple `terraform destroy -var-file=...`), noting that ASG resources are still Terraform-managed so teardown is one command.

6. **Outstanding fixes tracked today**
   - NAT bootstrap now installs iptables correctly and resets filter rules before starting the service (`infra/nat_instances.tf`).
   - Probe bootstrap no longer forces a conflicting `curl` install (`infra/test_probes.tf`).
   - `ISSUES_LOG.md` and `docs/demo-health-test-2025-10-26.json` capture the current state; revisit them before making further changes.
