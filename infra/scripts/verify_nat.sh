#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=${1:-test}
PROJECT=${2:-nat-alternative}
REGION=${AWS_REGION:-${3:-us-east-1}}

log() {
  printf '%s %s\n' "$(date --iso-8601=seconds)" "$*"
}

log "Checking NAT instance health in region ${REGION} for project ${PROJECT} (${ENVIRONMENT})"

nat_states=$(aws ec2 describe-instances \
  --region "${REGION}" \
  --filters "Name=tag:Project,Values=${PROJECT}" \
            "Name=tag:Environment,Values=${ENVIRONMENT}" \
            "Name=tag:Role,Values=nat" \
  --query 'Reservations[].Instances[].State.Name' \
  --output text)

if [[ -z "${nat_states}" ]]; then
  log "ERROR: No NAT instances found"
  exit 1
fi

for state in ${nat_states}; do
  if [[ "${state}" != "running" ]]; then
    log "ERROR: NAT instance state ${state} is not running"
    exit 1
  fi
done

log "NAT instances are running"

route_targets=$(aws ec2 describe-route-tables \
  --region "${REGION}" \
  --filters "Name=tag:Project,Values=${PROJECT}" \
            "Name=tag:Environment,Values=${ENVIRONMENT}" \
            "Name=tag:Tier,Values=private" \
  --query 'RouteTables[].Routes[?DestinationCidrBlock==`0.0.0.0/0`].NetworkInterfaceId' \
  --output text)

if [[ -z "${route_targets}" ]]; then
  log "ERROR: No default routes to NAT network interfaces found"
  exit 1
fi

for eni in ${route_targets}; do
  if [[ "${eni}" == "None" ]]; then
    log "ERROR: Found default route without network interface"
    exit 1
  fi
  log "Found default route via ENI ${eni}"
  aws ec2 describe-network-interfaces --region "${REGION}" --network-interface-ids "${eni}" \
    --query 'NetworkInterfaces[0].Attachment.InstanceId' --output text >/tmp/nat-instance-id
  nat_id=$(< /tmp/nat-instance-id)
  log "Default route bound to NAT instance ${nat_id}"
  rm -f /tmp/nat-instance-id
done

probe_json=$(terraform output -json probe_instance_ids 2>/dev/null || echo '{}')
if [[ $(echo "${probe_json}" | jq 'length') -gt 0 ]]; then
  log "Waiting for probe instances to terminate"
  ids=$(echo "${probe_json}" | jq -r '.[]')
  if [[ -n "${ids}" ]]; then
    aws ec2 wait instance-terminated --region "${REGION}" --instance-ids ${ids} || {
      log "WARNING: Timeout waiting for probe instances to terminate"
    }
  fi
fi

log "Verification completed"
