#!/usr/bin/env bash
set -euo pipefail

ENVIRONMENT=${1:-test}
PROJECT=${2:-nat-alternative}
REGION=${AWS_REGION:-${3:-eu-central-1}}
REQUIRE_NAT=${REQUIRE_NAT:-0}
REPORT_FILE=${REPORT_FILE:-verification-report.md}
INVOKE_LAMBDAS=${INVOKE_LAMBDAS:-1}
OUTPUT_DIR=$(dirname "${REPORT_FILE}")
PREFIX="${PROJECT}-${ENVIRONMENT}"
LOG_COLLECTOR_FUNCTION=${LOG_COLLECTOR_FUNCTION:-${PREFIX}-log-collector}
DEMO_HEALTH_FUNCTION=${DEMO_HEALTH_FUNCTION:-${PREFIX}-demo-health}
LOG_COLLECTOR_FILE=${LOG_COLLECTOR_FILE:-${OUTPUT_DIR}/log-collector-output.json}
DEMO_HEALTH_FILE=${DEMO_HEALTH_FILE:-${OUTPUT_DIR}/demo-health-output.json}

# Reset report file
: >"${REPORT_FILE}"

report_section() {
  printf '## %s\n\n' "$1" >>"${REPORT_FILE}"
}

report_block() {
  printf '```\n%s\n```\n\n' "$1" >>"${REPORT_FILE}"
}

append_kv() {
  printf '%s: %s\n' "$1" "$2" >>"${REPORT_FILE}"
}

append_line() {
  printf '%s\n' "$1" >>"${REPORT_FILE}"
}

summarize_log_collector() {
  if [[ "${INVOKE_LAMBDAS}" == "0" ]]; then
    report_section "Log Collector Summary"
    append_line "Invocation skipped (INVOKE_LAMBDAS=0)."
    append_line ""
    return
  fi

  if ! command -v jq >/dev/null 2>&1 || [[ ! -s "${LOG_COLLECTOR_FILE}" ]]; then
    report_section "Log Collector Summary"
    append_line "No log collector data available."
    append_line ""
    return
  fi

  local generated lookback
  generated=$(jq -r '.generatedAt // empty' "${LOG_COLLECTOR_FILE}")
  lookback=$(jq -r '.lookbackMinutes // empty' "${LOG_COLLECTOR_FILE}")

  report_section "Log Collector Summary"
  [[ -n "${generated}" ]] && append_line "Generated at: ${generated}"
  [[ -n "${lookback}" ]] && append_line "Lookback window: ${lookback} minutes"
  append_line ""

  if jq -e '.logGroups | length > 0' "${LOG_COLLECTOR_FILE}" >/dev/null 2>&1; then
    append_line "Log groups:"
    jq -r '.logGroups[] |
      "- \(.logGroup // "<unknown>"): \(.eventCount // 0) events (latest: " +
      ((.events | if length > 0 then .[-1].timestamp else "n/a" end)) +
      ", sample stream: " + (.events[0].logStream // "n/a") + ")"' \
      "${LOG_COLLECTOR_FILE}" >>"${REPORT_FILE}"
    append_line ""
  else
    append_line "No log groups returned."
    append_line ""
  fi

  append_line "Full payload saved to ${LOG_COLLECTOR_FILE}."
  append_line ""
}

summarize_demo_health() {
  if [[ "${INVOKE_LAMBDAS}" == "0" ]]; then
    report_section "Demo Health Summary"
    append_line "Invocation skipped (INVOKE_LAMBDAS=0)."
    append_line ""
    return
  fi

  if ! command -v jq >/dev/null 2>&1 || [[ ! -s "${DEMO_HEALTH_FILE}" ]]; then
    report_section "Demo Health Summary"
    append_line "No demo health data available."
    append_line ""
    return
  fi

  local generated lookback
  generated=$(jq -r '.generatedAt // empty' "${DEMO_HEALTH_FILE}")
  lookback=$(jq -r '.lookbackMinutes // empty' "${DEMO_HEALTH_FILE}")

  report_section "Demo Health Summary"
  [[ -n "${generated}" ]] && append_line "Generated at: ${generated}"
  [[ -n "${lookback}" ]] && append_line "Health lookback: ${lookback} minutes"
  append_line ""

  if jq -e '.natInstances | length > 0' "${DEMO_HEALTH_FILE}" >/dev/null 2>&1; then
    append_line "NAT instances (demo-health view):"
    jq -r '.natInstances[] |
      "- \(.instanceId) (\(.availabilityZone // "n/a")): state=\(.state // "n/a"), SSM=\(.ssmPingStatus // "n/a")"' \
      "${DEMO_HEALTH_FILE}" >>"${REPORT_FILE}"
    append_line ""
  fi

  if jq -e '.probeInstances | length > 0' "${DEMO_HEALTH_FILE}" >/dev/null 2>&1; then
    append_line "Probe instances (demo-health view):"
    jq -r '.probeInstances[] |
      "- \(.instanceId) (\(.availabilityZone // "n/a")): state=\(.state // "n/a"), SSM=\(.ssmPingStatus // "n/a")"' \
      "${DEMO_HEALTH_FILE}" >>"${REPORT_FILE}"
    append_line ""
  fi

  if jq -e '.logGroups | length > 0' "${DEMO_HEALTH_FILE}" >/dev/null 2>&1; then
    append_line "Log groups observed:"
    jq -r '.logGroups[] |
      "- \(.logGroup // "<unknown>"): latest event \(.latestEventTime // "n/a")"' \
      "${DEMO_HEALTH_FILE}" >>"${REPORT_FILE}"
    append_line ""
  fi

  if jq -e '.logCollector' "${DEMO_HEALTH_FILE}" >/dev/null 2>&1; then
    append_line "Embedded log collector (from demo-health):"
    jq -r '.logCollector |
      "- Window: \(.lookbackMinutes // 0) minutes, events sampled from \(.logGroups | length) log groups"' \
      "${DEMO_HEALTH_FILE}" >>"${REPORT_FILE}"
    append_line ""
  fi

  append_line "Full payload saved to ${DEMO_HEALTH_FILE}."
  append_line ""
}

invoke_lambda() {
  local function_name="$1"
  local payload="$2"
  local output_file="$3"
  local section_title="$4"

  if [[ "${INVOKE_LAMBDAS}" == "0" ]]; then
    printf '{}' >"${output_file}"
    return
  fi

  if ! aws lambda get-function --function-name "${function_name}" --region "${REGION}" >/dev/null 2>&1; then
    log "INFO: Lambda ${function_name} not found; skipping"
    printf '{}' >"${output_file}"
    return
  fi

  tmp_meta=$(mktemp)
  if aws lambda invoke \
    --cli-binary-format raw-in-base64-out \
    --function-name "${function_name}" \
    --payload "${payload}" \
    --region "${REGION}" \
    "${output_file}" \
    >"${tmp_meta}" 2>&1; then
    log "Lambda ${function_name} invoked; output saved to ${output_file}"
  else
    log "WARNING: Lambda ${function_name} invocation failed"
    printf '{}' >"${output_file}"
  fi
  rm -f "${tmp_meta}"
}

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
report_section "Verification Summary"
append_kv "Project" "${PROJECT}"
append_kv "Environment" "${ENVIRONMENT}"
append_kv "Region" "${REGION}"
printf '\n' >>"${REPORT_FILE}"

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

nat_table=$(aws ec2 describe-instances \
  --region "${REGION}" \
  --filters "Name=tag:Project,Values=${PROJECT}" \
            "Name=tag:Environment,Values=${ENVIRONMENT}" \
            "Name=tag:Role,Values=nat" \
  --query 'Reservations[].Instances[].{Id:InstanceId,AZ:Placement.AvailabilityZone,State:State.Name,SourceDest:SourceDestCheck,EIP:PublicIpAddress,PrivateIp:PrivateIpAddress,LaunchTime:LaunchTime}' \
  --output table)

report_section "NAT Instances"
report_block "$nat_table"

nat_ssm=$(aws ssm describe-instance-information \
  --region "${REGION}" \
  --filters "Key=InstanceIds,Values=$(IFS=,; echo "${nat_ids[*]}")" \
  --query 'InstanceInformationList[].{Id:InstanceId,PingStatus:PingStatus,LastPing:LastPingDateTime}' \
  --output table 2>/dev/null || true)

if [[ -n "${nat_ssm}" ]]; then
  report_section "NAT SSM Status"
  report_block "$nat_ssm"
fi

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

route_table_table=$(aws ec2 describe-route-tables \
  --region "${REGION}" \
  --filters "Name=tag:Project,Values=${PROJECT}" \
            "Name=tag:Environment,Values=${ENVIRONMENT}" \
            "Name=tag:Tier,Values=private" \
  --query 'RouteTables[].{RouteTableId:RouteTableId,Name:Tags[?Key==`Name`]|[0].Value,DefaultTarget:Routes[?DestinationCidrBlock==`0.0.0.0/0`]|[0].NetworkInterfaceId,Origin:Routes[?DestinationCidrBlock==`0.0.0.0/0`]|[0].Origin}' \
  --output table)

report_section "Private Route Tables"
report_block "$route_table_table"

probe_json=$(terraform output -json probe_instance_ids 2>/dev/null || echo '{}')
if [[ $(echo "${probe_json}" | jq 'length') -gt 0 ]]; then
  probe_ids=()
  while IFS= read -r line; do
    [[ -n "${line}" ]] && probe_ids+=("${line}")
  done < <(echo "${probe_json}" | jq -r '.[]')

  if [[ ${#probe_ids[@]} -eq 0 ]]; then
    log "No probe instances reported by Terraform output; skipping probe checks"
    report_section "Probe Instances"
    append_line "No probe instances reported by Terraform outputs."
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

    probe_table=$(aws ec2 describe-instances \
      --region "${REGION}" \
      --instance-ids "${probe_ids[@]}" \
      --query 'Reservations[].Instances[].{Id:InstanceId,AZ:Placement.AvailabilityZone,State:State.Name,PrivateIp:PrivateIpAddress,LaunchTime:LaunchTime}' \
      --output table)

    report_section "Probe Instances"
    report_block "$probe_table"

    ssm_instances=$(aws ssm describe-instance-information \
      --region "${REGION}" \
      --filters "Key=InstanceIds,Values=$(IFS=,; echo "${probe_ids[*]}")" \
      --query 'InstanceInformationList[].{Id:InstanceId,PingStatus:PingStatus,LastPing:LastPingDateTime}' \
      --output table 2>/dev/null || true)

    if [[ -n "${ssm_instances}" ]]; then
      report_section "Probe SSM Status"
      report_block "$ssm_instances"
    fi
  fi
fi

invoke_lambda "${LOG_COLLECTOR_FUNCTION}" '{"lookback_minutes":30,"max_events":50}' "${LOG_COLLECTOR_FILE}" "Log Collector Lambda Output"
invoke_lambda "${DEMO_HEALTH_FUNCTION}" '{"lookback_minutes":30}' "${DEMO_HEALTH_FILE}" "Demo Health Lambda Output"

summarize_log_collector
summarize_demo_health

log "Verification completed"
log "Report written to ${REPORT_FILE}"
append_line "Report generated: ${REPORT_FILE}"
