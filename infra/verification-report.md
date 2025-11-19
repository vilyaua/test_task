## Verification Summary

Project: nat-alternative
Environment: test
Region: eu-central-1

## NAT Instances

```
-----------------------------------------------------------------------------------------------------------------------------------
|                                                        DescribeInstances                                                        |
+---------------+-----------------+----------------------+----------------------------+-------------+--------------+--------------+
|      AZ       |       EIP       |         Id           |        LaunchTime          |  PrivateIp  | SourceDest   |    State     |
+---------------+-----------------+----------------------+----------------------------+-------------+--------------+--------------+
|  eu-central-1a|  None           |  i-0a4cbba7f642cb5c1 |  2025-10-27T12:36:41+00:00 |  None       |  None        |  terminated  |
|  eu-central-1b|  None           |  i-0a41bcefaead5b49c |  2025-10-27T12:36:39+00:00 |  None       |  None        |  terminated  |
|  eu-central-1b|  3.69.202.20    |  i-087293a688fab22ea |  2025-10-27T13:02:33+00:00 |  10.0.17.39 |  False       |  running     |
|  eu-central-1a|  18.199.114.194 |  i-09a078d397a1471df |  2025-10-27T13:02:34+00:00 |  10.0.5.14  |  False       |  running     |
+---------------+-----------------+----------------------+----------------------------+-------------+--------------+--------------+
```

## NAT SSM Status

```
---------------------------------------------------------------------------
|                       DescribeInstanceInformation                       |
+----------------------+------------------------------------+-------------+
|          Id          |             LastPing               | PingStatus  |
+----------------------+------------------------------------+-------------+
|  i-087293a688fab22ea |  2025-10-27T14:02:51.257000+01:00  |  Online     |
|  i-09a078d397a1471df |  2025-10-27T14:03:45.326000+01:00  |  Online     |
+----------------------+------------------------------------+-------------+
```

## Private Route Tables

```
--------------------------------------------------------------------------------------------------------------------
|                                                DescribeRouteTables                                               |
+-----------------------+-------------------------------------------------+--------------+-------------------------+
|     DefaultTarget     |                      Name                       |   Origin     |      RouteTableId       |
+-----------------------+-------------------------------------------------+--------------+-------------------------+
|  eni-04f4254c3e7cfa830|  nat-alternative-test-private-rt-eu-central-1a  |  CreateRoute |  rtb-044fccd21c2f5b8d1  |
|  eni-0b3c68403cffb65d3|  nat-alternative-test-private-rt-eu-central-1b  |  CreateRoute |  rtb-0030a5d047c941ad6  |
+-----------------------+-------------------------------------------------+--------------+-------------------------+
```

## Probe Instances

```
-------------------------------------------------------------------------------------------------
|                                       DescribeInstances                                       |
+---------------+----------------------+-----------------------------+--------------+-----------+
|      AZ       |         Id           |         LaunchTime          |  PrivateIp   |   State   |
+---------------+----------------------+-----------------------------+--------------+-----------+
|  eu-central-1a|  i-0de4c8601994b038a |  2025-10-27T13:02:48+00:00  |  10.0.38.38  |  running  |
|  eu-central-1b|  i-0615bb1da812dcfaf |  2025-10-27T13:02:48+00:00  |  10.0.50.240 |  running  |
+---------------+----------------------+-----------------------------+--------------+-----------+
```

## Probe SSM Status

```
---------------------------------------------------------------------------
|                       DescribeInstanceInformation                       |
+----------------------+------------------------------------+-------------+
|          Id          |             LastPing               | PingStatus  |
+----------------------+------------------------------------+-------------+
|  i-0615bb1da812dcfaf |  2025-10-27T14:03:26.357000+01:00  |  Online     |
|  i-0de4c8601994b038a |  2025-10-27T14:03:21.306000+01:00  |  Online     |
+----------------------+------------------------------------+-------------+
```

## Log Collector Summary

Generated at: 2025-10-27T13:04:57.336310+00:00
Lookback window: 30 minutes

Log groups:
- /nat/nat-alternative-test/nat: 50 events (latest: 2025-10-27T13:03:17.447000+00:00, sample stream: nat-i-087293a688fab22ea)
- /nat/nat-alternative-test/probe: 48 events (latest: 2025-10-27T13:03:52+00:00, sample stream: probe-i-0de4c8601994b038a)

Full payload saved to ./log-collector-output.json.

## Demo Health Summary

Generated at: 2025-10-27T13:05:03.749416+00:00
Health lookback: 30 minutes

NAT instances (demo-health view):
- i-087293a688fab22ea (eu-central-1b): state=running, SSM=Online
- i-09a078d397a1471df (eu-central-1a): state=running, SSM=Online

Probe instances (demo-health view):
- i-0de4c8601994b038a (eu-central-1a): state=running, SSM=Online
- i-0615bb1da812dcfaf (eu-central-1b): state=running, SSM=Online

Log groups observed:
- /aws/vpc/nat-alternative-test: latest event 2025-10-27T13:03:09+00:00
- /nat/nat-alternative-test/nat: latest event 2025-10-27T13:03:17.448000+00:00
- /nat/nat-alternative-test/probe: latest event 2025-10-27T13:03:46+00:00
- /aws/lambda/nat-alternative-test-log-collector: latest event n/a

Embedded log collector (from demo-health):
- Window: 30 minutes, events sampled from 2 log groups

Full payload saved to ./demo-health-output.json.

Report generated: verification-report.md
