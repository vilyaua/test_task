# Highly Available AWS NAT Gateway Alternative

## 1. Goals and Constraints
- Provide outbound internet access for private subnets without exposing inbound paths.
- Remain available during AZ, instance, or configuration failures.
- Use AWS-native building blocks for automation, observability, and security.
- Control costs compared to managed NAT gateways while keeping operations lightweight.

## 2. Architecture Summary
Private subnets in each Availability Zone forward default traffic (0.0.0.0/0) to a Network Load Balancer. The NLB targets a fleet of NAT EC2 instances, one per AZ, deployed via Auto Scaling Groups. Each NAT instance enables IP forwarding and iptables-based masquerading. An Internet Gateway provides public egress, while Lambda functions act as the control plane for health checks, failover, lifecycle management, and configuration drift prevention. Observability is delivered through CloudWatch metrics/alarms and VPC Flow Logs stored in CloudWatch Logs or S3. The overall flow is depicted in `architecture-diagram.mmd`.

## 3. Data Plane Components
- **NAT Instances (EC2 + ASG):**
  - Launch templates configure Amazon Linux 2023 with `ip_forward=1`, `iptables` masquerade rules, SSM agent, and CloudWatch agent.
  - Auto Scaling Groups ensure at least one warm instance per AZ; optional scale-out on connection count (CloudWatch metric via custom script).
  - Security groups allow ingress from private subnets and health checks, egress to the internet, and SSM endpoints. No inbound from the internet.
- **Network Load Balancer:**
  - Provides static IPs per AZ and cross-zone failover while preserving source IPs.
  - Targets registered through ASG lifecycle hooks or Lambda.
  - Health checks on HTTPS endpoint (instance metadata proxy) or TCP port verifying iptables NAT path.
- **Route Tables:**
  - Each private subnet uses an AZ-local route table pointing default routes to the NLB.
  - Lambda failover logic can shift specific route tables to alternate AZ targets during failures, minimizing blast radius.
- **Internet Gateway & Elastic IPs:**
  - IGW required for outbound internet path.
  - Optional Elastic IPs attached to NLB if static egress addresses are required; otherwise rely on NLB-managed IPs.

## 4. Control Plane Automation (AWS Lambda)
- **nat-health-probe:** Scheduled by EventBridge to test each NAT instance's ability to reach known endpoints (e.g., `1.1.1.1`, `aws.amazon.com`). Publishes CloudWatch metrics (`NATReachability`, `Latency`).
- **nat-route-failover:** Triggered by alarm on `NATReachability`. Updates route tables or NLB target group weights so healthy instances receive traffic. Optionally integrates with AWS Systems Manager Parameter Store for routing state.
- **asg-lifecycle-handler:** Subscribed to Auto Scaling lifecycle hooks for `launch` and `terminate`. Registers/deregisters instances with the NLB, validates configuration via SSM, and releases lifecycle actions.
- **eip-recover:** (If using Elastic IPs instead of NLB) reassociates EIPs when instances fail, ensuring continuity of outbound address.
- **config-guard:** Uses SSM State Manager or EventBridge schedule to confirm sysctl/iptables rules and replace drifted values.

All Lambdas share a logging layer (CloudWatch Logs, structured JSON) and emit metrics. They use least-privilege IAM roles granting only the required EC2, ELB, EC2:ModifyRouteTable, and SSM permissions.

## 5. Monitoring, Logging, and Alerting
- **CloudWatch Metrics & Alarms:** Monitor instance health checks, connection tracking, CPU, and the custom reachability metric. Alarms notify via SNS/ChatOps.
- **VPC Flow Logs:** Capture traffic patterns and anomalies; centralized to S3 with lifecycle policies and optional Athena queries for investigations.
- **CloudWatch Logs & Traces:** NAT instances push system logs via CloudWatch Agent. Lambda functions emit structured logs for troubleshooting automation decisions.
- **Synthetic Monitoring:** Optional Route 53 health checks or AWS CloudWatch Synthetics to simulate outbound calls through each AZ.

## 6. Security Considerations
- **IAM:** Separate roles for Lambda, NAT instances, and CI/CD pipeline. Enforce least privilege and use IAM Access Analyzer to validate policies.
- **Network:** Security groups restrict inbound sources to private subnet CIDR blocks and AWS health check IPs. NACLs remain stateless backups.
- **Patch Management:** Use SSM Patch Manager to keep NAT AMIs current. Rotate instance credentials using SSM Parameter Store or Secrets Manager.
- **Encryption:** Enable TLS for management APIs, use KMS for encrypting logs and parameters. NAT instances store minimal state, simplifying rotation.
- **Compliance:** Enable AWS Config rules to verify resources (e.g., ensure subnets route to NLB, ASGs maintain desired capacity).

## 7. Scalability and Resilience
- **Horizontal Scaling:** ASGs scale out additional NAT instances when connection tracking or bandwidth approaches thresholds; NLB automatically balances traffic.
- **Multi-AZ Resilience:** Each AZ has a primary NAT, but route tables can be updated to use other AZs on failure. Keep warm capacity in secondary AZs for rapid take-over.
- **Failure Detection:** Combine NLB health checks, CloudWatch metrics, and Lambda synthetic probes to reduce false positives.
- **Testing:** Regularly run game days injecting failures (stop instance, disable IP forwarding) to validate automation.

## 8. Cost and Operational Trade-Offs
- **Pros vs Managed NAT Gateway:** Lower per-hour and per-GB costs, full control over instance type, ability to use Spot or Graviton. Requires ongoing management.
- **NLB vs Elastic IP Routing:**
  - *NLB Mode:* Simplifies cross-AZ failover, provides static IPs per AZ, but incurs NLB hourly/data-processing charges.
  - *EIP Mode:* Eliminates NLB cost; Lambda must reassign EIPs per AZ and adjust route tables, increasing control plane complexity and failover time.
- **Instance Selection:** Use `c7g.large` or `m7g.large` with ENA for throughput; evaluate Spot for secondary AZ capacity with interruption handling.
- **Operational Load:** Automation reduces toil but still requires monitoring updates, AMI refresh, and patching.

## 9. Deployment & CI/CD Hints
- Use Terraform modules to define VPC, NLB, ASGs, and Lambda functions. Parameterize per environment (CIDRs, AZ lists, instance types).
- GitHub Actions pipeline stages:
  1. `terraform fmt`, `tflint`, `tfsec`.
  2. `terraform plan` against test account.
  3. Automated deployment to test, run integration checks.
  4. Manual approval for production apply.
- Store Lambda code in repository; use SAM/Serverless Framework packaging step within CI.

## 10. Operational Playbook
- **Failover:** When health alarms fire, Lambda `nat-route-failover` updates routes/NLB weights within ~60 seconds (RTO). RPO is near-zero due to stateless design.
- **Maintenance:** Drain traffic via ASG lifecycle hook, patch instance, then resume. Rotate AMIs quarterly.
- **Incident Response:** On-call dashboard showing per-AZ health, connection counts, and alarm status. Document manual override (e.g., CLI script to point routes to standby NAT).
- **Logging & Retention:** Retain flow logs 90 days (S3 lifecycle to Glacier). CloudWatch Logs retention 30 days by default; export critical logs to S3 for long-term storage.

## 11. Future Enhancements
- Add AWS Network Firewall or third-party appliances behind the NLB for deep packet inspection.
- Integrate GuardDuty findings to automatically isolate compromised instances.
- Evaluate Gateway Load Balancer as an alternative for traffic steering if adding advanced security appliances.

