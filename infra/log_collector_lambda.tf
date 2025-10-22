data "archive_file" "log_collector" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/log_collector"
  output_path = "${path.module}/lambda/log_collector.zip"
}

data "aws_iam_policy_document" "log_collector_assume" {
  statement {
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
      "logs:DescribeLogGroups",
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
