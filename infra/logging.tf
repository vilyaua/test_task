data "aws_caller_identity" "current" {}

data "aws_kms_key" "logs_alias" {
  count  = var.logs_kms_key_arn == "" && var.logs_kms_key_alias != "" ? 1 : 0
  key_id = var.logs_kms_key_alias
}

data "aws_iam_policy_document" "logs_kms" {
  count = var.logs_kms_key_arn == "" && var.logs_kms_key_alias == "" ? 1 : 0

  statement {
    sid    = "EnableRootAccountAccess"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:root"]
    }

    actions   = ["kms:*"]
    resources = ["*"]
  }

  statement {
    sid    = "AllowCloudWatchLogsEncryption"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["logs.${var.aws_region}.amazonaws.com"]
    }

    actions = [
      "kms:Encrypt*",
      "kms:Decrypt",
      "kms:ReEncrypt*",
      "kms:GenerateDataKey*",
      "kms:DescribeKey"
    ]

    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "kms:EncryptionContext:aws:logs:arn"
      values = [
        "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vpc/${local.prefix}"
      ]
    }
  }
}

resource "aws_kms_key" "logs" {
  count = var.logs_kms_key_arn == "" && var.logs_kms_key_alias == "" ? 1 : 0

  description         = "KMS key for ${local.prefix} VPC flow logs"
  enable_key_rotation = true
  policy              = data.aws_iam_policy_document.logs_kms[0].json

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-logs-kms"
  })
}

locals {
  flow_logs_kms_arn = compact([
    var.logs_kms_key_arn,
    var.logs_kms_key_alias != "" ? data.aws_kms_key.logs_alias[0].arn : "",
    try(aws_kms_key.logs[0].arn, "")
  ])[0]
}

resource "aws_cloudwatch_log_group" "vpc_flow" {
  name              = "/aws/vpc/${local.prefix}"
  retention_in_days = var.flow_log_retention_days
  kms_key_id        = local.flow_logs_kms_arn

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-flowlogs"
  })
}

resource "aws_iam_role" "flow_logs" {
  name               = "${local.prefix}-flowlogs-role"
  assume_role_policy = data.aws_iam_policy_document.flow_logs_assume.json

  tags = local.base_tags
}

data "aws_iam_policy_document" "flow_logs_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["vpc-flow-logs.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role_policy" "flow_logs" {
  name   = "${local.prefix}-flowlogs-policy"
  role   = aws_iam_role.flow_logs.id
  policy = data.aws_iam_policy_document.flow_logs_permissions.json
}

data "aws_iam_policy_document" "flow_logs_permissions" {
  statement {
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
      "logs:PutLogEvents"
    ]

    resources = [
      aws_cloudwatch_log_group.vpc_flow.arn,
      "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/vpc/${local.prefix}:log-stream:*"
    ]
  }

  statement {
    effect    = "Allow"
    actions   = ["logs:CreateLogGroup"]
    resources = [aws_cloudwatch_log_group.vpc_flow.arn]
  }
}

resource "aws_flow_log" "vpc" {
  log_destination      = aws_cloudwatch_log_group.vpc_flow.arn
  log_destination_type = "cloud-watch-logs"
  traffic_type         = "ALL"
  iam_role_arn         = aws_iam_role.flow_logs.arn
  vpc_id               = aws_vpc.this.id

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-flowlog"
  })
}
