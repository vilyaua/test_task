## Next Steps for Demo Automation

1. **Harden the new ASG + hook workflow**
   - Add CloudWatch metrics/alarms on the Lambda (`nat-asg-hook`) so misfires are visible.
   - Create a simple runbook/automation script to force an ASG instance refresh and capture the resulting logs for demos.
   - Consider adding integration tests (e.g., via GitHub Actions) that simulate the EventBridge payload to ensure the hook continues to associate Elastic IPs and update routes as expected.

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
