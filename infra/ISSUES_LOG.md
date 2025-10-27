# Issue Log

Tracks infra defects identified during operations, alongside the applied fixes and references to the source files that changed.

# 2025-10-27

- **NAT ASG hook failed to prepare replacement instances**  
  - *Symptoms*: After switching NAT hosts to an Auto Scaling Group, new instances kept `SourceDestCheck=true`, private route tables lost their 0.0.0.0/0 targets, and probe instances never reached SSM (`PingStatus: Unknown`). EventBridge showed the hook firing but CloudWatch logs recorded `ValueError` about missing Availability Zones.  
  - *Cause*: Auto Scaling’s launch-success events sometimes emit the AZ under `detail["Details"]["Availability Zone"]`. The original hook only read `detail["AvailabilityZone"]`, so it bailed out before disabling source/dest checks or recreating the default route.  
  - *Fix*: Updated `infra/lambda/nat_asg_hook/main.py` to pull the AZ from all known fields, disable source/dest checks via `ec2:ModifyInstanceAttribute`, and fall back to `CreateRoute` when the default route is absent. Expanded the hook IAM policy in `infra/nat_asg_automation.tf` and forced NAT ASGs to depend on the hook/EventBridge resources (`infra/nat_instances.tf`) so the first launch happens only after automation is in place.

## 2025-10-26

- **Probe bootstrap stalled on `curl` package conflicts**  
  - *Symptoms*: Freshly deployed probes failed to generate CloudWatch log streams, and `/var/log/nat-probe.log` captured repeated `dnf` errors complaining that `curl` conflicts with the preinstalled `curl-minimal`.  
  - *Cause*: `infra/test_probes.tf:13-28` forcibly installed the full `curl` package even though Amazon Linux 2023 already bundles `curl-minimal`. With `set -euo pipefail`, the failed `dnf install -y curl bind-utils traceroute` aborted the rest of the user data before CloudWatch Agent or the traffic probes started.  
  - *Fix*: Dropped the redundant `curl` install (only `bind-utils` and `traceroute` remain) so the script relies on the built-in binary, allowing the probe automation and logging stack to complete.

- **NAT bootstrap aborted before configuring SNAT/SSM**  
  - *Symptoms*: Probe instances could not reach the internet or register in SSM; `dnf` in user data failed with “No match for argument: iptables-nft-services,” and the script exited early due to `set -euo pipefail`.  
  - *Cause*: `infra/nat_instances.tf:14-44` attempted to install the nonexistent `iptables-nft-services` package and redundantly reinstalled `curl`, which conflicts with the default `curl-minimal` in AL2023.  
  - *Fix*: Switched the package list to the real AL2023 packages (`iptables-nft`, `iptables-services`) and left curl untouched; also auto-detect the default interface before applying the masquerade rule so SNAT always targets the live ENI.

- **Linux filter table blocking all forwarded traffic**  
  - *Symptoms*: Even after the SNAT fix, probes still showed `curl error (7)` to AWS repos and never appeared in SSM; `iptables -L FORWARD` on the NAT instances revealed the default `REJECT ... reject-with icmp-host-prohibited` rule created by AL2023.  
  - *Cause*: The bootstrap only touched the `nat` table; the default filter policy remained `REJECT`, so packets leaving private subnets were dropped before NAT processing. Additionally, `systemctl enable --now iptables` started the service before custom rules were applied, causing the default REJECT rule to be persisted.  
  - *Fix*: Reordered the bootstrap in `infra/nat_instances.tf:44-58` to configure filter/NAT rules first, save them, and then restart the iptables service. The script now explicitly flushes `FORWARD`, sets the policy to `ACCEPT`, writes `/etc/sysconfig/iptables`, and only then reloads the service, making the NAT host actually forward traffic.

## 2025-10-23

- **CloudWatch Logs/KMS handshake failures**  
  - *Symptoms*: Flow-log and application log groups intermittently failed to encrypt or describe the managed KMS key, emitting `AccessDeniedException` for `kms:DescribeKey`.  
  - *Cause*: The custom key policy in `infra/logging.tf:39-86` granted the CloudWatch Logs service Encrypt/Decrypt rights but omitted `kms:DescribeKey`, which AWS requires when attaching encrypted log groups.  
  - *Fix*: Reworked the policy to split Encrypt/ReEncrypt actions from DescribeKey and added a dedicated statement permitting `logs.<region>.amazonaws.com` to call `kms:DescribeKey`, restoring log group provisioning.

## 2025-10-22

- **Private route table tagging drift**  
  - *Symptoms*: The `verify_nat.sh` script and CI workflows filtered route tables by `Tier=private` and failed to find any, leading to false alarms that no 0.0.0.0/0 routes pointed at NAT ENIs.  
  - *Cause*: `infra/network.tf:69-78` created private route tables with `Name` tags only; without a `Tier` tag, AWS CLI filters returned zero results.  
  - *Fix*: Added `Tier = "private"` to the tag map so every route table carries the filter key the scripts expect.

- **SSM log collection using wrong region**  
  - *Symptoms*: The `prepare-for-demo` GitHub Action attempted to pull probe logs via SSM but the step crashed with “region must be specified,” halting the workflow after validation.  
  - *Cause*: The workflow referenced `${{ secrets.AWS_REGION }}` even though the pipeline had migrated to GitHub environment variables; secrets were blank in the demo org.  
  - *Fix*: Updated `.github/workflows/prepare-for-demo.yml:154` (commit `41d9b24`) and the accompanying docs to read `${{ vars.AWS_REGION }}`, aligning the workflow with the new configuration source.

- **Environment CIDR overlap between test/prod**  
  - *Symptoms*: Planning both environments in the same account produced VPC CIDR overlap warnings, blocking shared networking tests and risked future peering conflicts.  
  - *Cause*: Both `environments/test/vars.tfvars` and `environments/prod/vars.tfvars` defaulted to `10.0.0.0/16`.  
  - *Fix*: Assigned unique ranges (`10.0.0.0/16` for test, `10.1.0.0/16` for prod) and documented the separation in `README.md` so future environments avoid collisions.
