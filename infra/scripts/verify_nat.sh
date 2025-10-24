#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=${1:-test}
PROJECT=${2:-nat-alternative}
REGION=${AWS_REGION:-${3:-eu-central-1}}
REQUIRE_NAT=${REQUIRE_NAT:-0}

timestamp() {
  if command -v gdate >/dev/null 2>&1; then
    gdate -u +"%Y-%m-%dT%H:%M:%SZ"
  else
    date -u +"%Y-%m-%dT%H:%M:%SZ"
  fi
}

log() {
  printf '%s %s\n' "$(timestamp)" "$*"
}

log "Checking NAT instance health in region ${REGION} for project ${PROJECT} (${ENVIRONMENT})"

# Collect NAT instances
_nat_ids=$(aws ec2 describe-instances \
  --region "${REGION}" \
  --filters "Name=tag:Project,Values=${PROJECT}" \
            "Name=tag:Environment,Values=${ENVIRONMENT}" \
            "Name=tag:Role,Values=nat" \
  --query 'Reservations[].Instances[].InstanceId' \
  --output text)

if [[ -z "${_nat_ids}" ]]; then
  if [[ "${REQUIRE_NAT}" == "1" ]]; then
    log "ERROR: No NAT instances found"
    exit 1
  else
    log "INFO: No NAT instances found; skipping further checks"
    exit 0
  fi
fi

# shellcheck disable=SC2206
nat_ids=(${_nat_ids})

nat_state_output=$(aws ec2 describe-instances \
  --region "${REGION}" \
  --instance-ids "${nat_ids[@]}" \
  --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}' \
  --output json)

for row in $(echo "$nat_state_output" | jq -c '.[]'); do
  id=$(echo "$row" | jq -r '.Id')
  state=$(echo "$row" | jq -r '.State')
  if [[ "$state" != "running" ]]; then
    msg="NAT instance ${id} is ${state}"
    if [[ "${REQUIRE_NAT}" == "1" ]]; then
      log "ERROR: $msg"
      exit 1
    else
      log "WARNING: $msg"
    fi
  else
    log "NAT instance ${id} is running"
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
  if [[ "${REQUIRE_NAT}" == "1" ]]; then
    log "ERROR: No default routes to NAT network interfaces found"
    exit 1
  else
    log "INFO: No private routes pointing to NAT interfaces; skipping"
    exit 0
  fi
fi

for eni in ${route_targets}; do
  if [[ "${eni}" == "None" ]]; then
    if [[ "${REQUIRE_NAT}" == "1" ]]; then
      log "ERROR: Found default route without network interface"
      exit 1
    else
      log "WARNING: Found default route without network interface"
      continue
    fi
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
  probe_ids=()
  while IFS= read -r line; do
    [[ -n "${line}" ]] && probe_ids+=("${line}")
  done < <(echo "${probe_json}" | jq -r '.[]')

  if [[ ${#probe_ids[@]} -eq 0 ]]; then
    log "No probe instances reported by Terraform output; skipping probe checks"
  else
    log "Checking probe instance states: ${probe_ids[*]}"
    probe_state_output=$(aws ec2 describe-instances \
      --region "${REGION}" \
      --instance-ids "${probe_ids[@]}" \
      --query 'Reservations[].Instances[].{Id:InstanceId,State:State.Name}' \
      --output json)

    for row in $(echo "$probe_state_output" | jq -c '.[]'); do
      id=$(echo "$row" | jq -r '.Id')
      state=$(echo "$row" | jq -r '.State')
      log "Probe instance ${id} is ${state}"
    done
  fi
fi

log "Verification completed"
