data "archive_file" "log_collector" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/log_collector"
  output_path = "${path.module}/lambda/log_collector.zip"
}

data "aws_iam_policy_document" "log_collector_assume" {
  statement { #tfsec:ignore:aws-iam-no-policy-wildcards logs:DescribeLogGroups requires wildcard resource in AWS.
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "log_collector" {
  name               = "${local.prefix}-log-collector-role"
  assume_role_policy = data.aws_iam_policy_document.log_collector_assume.json

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-log-collector-role"
  })
}

resource "aws_iam_role_policy_attachment" "log_collector_basic" {
  role       = aws_iam_role.log_collector.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy_attachment" "log_collector_xray" {
  role       = aws_iam_role.log_collector.name
  policy_arn = "arn:aws:iam::aws:policy/AWSXRayDaemonWriteAccess"
}

data "aws_iam_policy_document" "log_collector_permissions" {
  statement {
    effect = "Allow"
    actions = [
      "logs:DescribeLogGroups"
    ]

    resources = ["*"]
  }

  #tfsec:ignore:aws-iam-no-policy-wildcards log streams require the :* suffix to grant read access.
  statement {
    effect = "Allow"
    actions = [
      "logs:DescribeLogStreams",
      "logs:GetLogEvents",
      "logs:FilterLogEvents"
    ]

    resources = [
      aws_cloudwatch_log_group.nat_instances.arn,
      "${aws_cloudwatch_log_group.nat_instances.arn}:*",
      aws_cloudwatch_log_group.probes.arn,
      "${aws_cloudwatch_log_group.probes.arn}:*"
    ]
  }
}

resource "aws_iam_role_policy" "log_collector" {
  name   = "${local.prefix}-log-collector-policy"
  role   = aws_iam_role.log_collector.id
  policy = data.aws_iam_policy_document.log_collector_permissions.json
}

resource "aws_lambda_function" "log_collector" {
  function_name = "${local.prefix}-log-collector"
  role          = aws_iam_role.log_collector.arn
  handler       = "main.handler"
  runtime       = "python3.12"

  filename         = data.archive_file.log_collector.output_path
  source_code_hash = data.archive_file.log_collector.output_base64sha256

  timeout = 30

  environment {
    variables = {
      LOG_GROUPS       = join(",", [aws_cloudwatch_log_group.nat_instances.name, aws_cloudwatch_log_group.probes.name])
      LOOKBACK_MINUTES = "15"
      MAX_EVENTS       = "200"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-log-collector"
  })
}

resource "aws_cloudwatch_log_group" "log_collector_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.log_collector.function_name}"
  retention_in_days = var.app_log_retention_days
  kms_key_id        = local.flow_logs_kms_arn

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-log-collector-lg"
  })
}

data "archive_file" "demo_health" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/demo_health"
  output_path = "${path.module}/lambda/demo_health.zip"
}

data "aws_iam_policy_document" "demo_health_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "demo_health" {
  name               = "${local.prefix}-demo-health-role"
  assume_role_policy = data.aws_iam_policy_document.demo_health_assume.json

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-demo-health-role"
  })
}

resource "aws_iam_role_policy_attachment" "demo_health_basic" {
  role       = aws_iam_role.demo_health.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

#tfsec:ignore:aws-iam-no-policy-wildcards demo health checks require wildcard access to read log streams.
resource "aws_iam_role_policy" "demo_health" {
  name = "${local.prefix}-demo-health-policy"
  role = aws_iam_role.demo_health.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["ssm:DescribeInstanceInformation"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "logs:DescribeLogStreams",
          "logs:GetLogEvents"
        ]
        Resource = [
          aws_cloudwatch_log_group.nat_instances.arn,
          "${aws_cloudwatch_log_group.nat_instances.arn}:*",
          aws_cloudwatch_log_group.probes.arn,
          "${aws_cloudwatch_log_group.probes.arn}:*",
          aws_cloudwatch_log_group.vpc_flow.arn,
          "${aws_cloudwatch_log_group.vpc_flow.arn}:*",
          aws_cloudwatch_log_group.log_collector_lambda.arn,
          "${aws_cloudwatch_log_group.log_collector_lambda.arn}:*"
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["lambda:InvokeFunction"]
        Resource = [aws_lambda_function.log_collector.arn]
      }
    ]
  })
}

resource "aws_lambda_function" "demo_health" {
  function_name = "${local.prefix}-demo-health"
  role          = aws_iam_role.demo_health.arn
  handler       = "main.handler"
  runtime       = "python3.12"

  filename         = data.archive_file.demo_health.output_path
  source_code_hash = data.archive_file.demo_health.output_base64sha256

  timeout = 30

  environment {
    variables = {
      PROJECT_TAG            = var.project
      ENVIRONMENT_TAG        = var.environment
      LOG_COLLECTOR_FUNCTION = aws_lambda_function.log_collector.function_name
      LOOKBACK_MINUTES       = "30"
    }
  }

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-demo-health"
  })
}

resource "aws_cloudwatch_log_group" "demo_health_lambda" {
  name              = "/aws/lambda/${aws_lambda_function.demo_health.function_name}"
  retention_in_days = var.app_log_retention_days
  kms_key_id        = local.flow_logs_kms_arn

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-demo-health-lg"
  })
}
