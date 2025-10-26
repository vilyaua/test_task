locals {
  nat_route_table_map    = { for az, rt in aws_route_table.private : az => rt.id }
  nat_route_table_arns   = [for rt in aws_route_table.private : rt.arn]
  nat_eip_allocation_map = { for az, eip in aws_eip.nat : az => eip.id }
  nat_eip_arns           = [for eip in aws_eip.nat : eip.arn]
  nat_asg_names          = [for asg in aws_autoscaling_group.nat : asg.name]
}

data "archive_file" "nat_asg_hook" {
  type        = "zip"
  source_dir  = "${path.module}/lambda/nat_asg_hook"
  output_path = "${path.module}/lambda/nat_asg_hook.zip"
}

data "aws_iam_policy_document" "nat_asg_hook_assume" {
  statement {
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "nat_asg_hook" {
  name               = "${local.prefix}-nat-asg-hook-role"
  assume_role_policy = data.aws_iam_policy_document.nat_asg_hook_assume.json

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-asg-hook-role"
  })
}

data "aws_iam_policy_document" "nat_asg_hook" {
  statement {
    effect = "Allow"
    actions = [
      "ec2:DescribeInstances"
    ]
    resources = ["*"] # DescribeInstances does not support resource-level restrictions.
  }

  statement {
    effect    = "Allow"
    actions   = ["ec2:ReplaceRoute"]
    resources = local.nat_route_table_arns
  }

  statement {
    effect    = "Allow"
    actions   = ["ec2:AssociateAddress"]
    resources = local.nat_eip_arns
  }
}

resource "aws_iam_role_policy_attachment" "nat_asg_hook_logs" {
  role       = aws_iam_role.nat_asg_hook.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_iam_role_policy" "nat_asg_hook" {
  name   = "${local.prefix}-nat-asg-hook-policy"
  role   = aws_iam_role.nat_asg_hook.id
  policy = data.aws_iam_policy_document.nat_asg_hook.json
}

resource "aws_lambda_function" "nat_asg_hook" {
  function_name = "${local.prefix}-nat-asg-hook"
  role          = aws_iam_role.nat_asg_hook.arn
  handler       = "main.handler"
  runtime       = "python3.12"

  filename         = data.archive_file.nat_asg_hook.output_path
  source_code_hash = data.archive_file.nat_asg_hook.output_base64sha256

  environment {
    variables = {
      PROJECT         = var.project
      ENVIRONMENT     = var.environment
      ROUTE_TABLE_MAP = jsonencode(local.nat_route_table_map)
      EIP_MAP         = jsonencode({ for az, eip in aws_eip.nat : az => eip.allocation_id })
    }
  }

  timeout = 60

  tracing_config {
    mode = "Active"
  }

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-asg-hook"
  })
}

resource "aws_cloudwatch_log_group" "nat_asg_hook" {
  name              = "/aws/lambda/${aws_lambda_function.nat_asg_hook.function_name}"
  retention_in_days = var.app_log_retention_days
  kms_key_id        = local.flow_logs_kms_arn

  tags = merge(local.base_tags, {
    Name = "${local.prefix}-nat-asg-hook-lg"
  })
}

resource "aws_cloudwatch_event_rule" "nat_asg_hook" {
  name        = "${local.prefix}-nat-asg-launch"
  description = "Invoke Lambda when NAT ASG instances launch successfully."

  event_pattern = jsonencode({
    "source" : ["aws.autoscaling"],
    "detail-type" : ["EC2 Instance Launch Successful"],
    "detail" : {
      "AutoScalingGroupName" : local.nat_asg_names
    }
  })
}

resource "aws_cloudwatch_event_target" "nat_asg_hook" {
  rule      = aws_cloudwatch_event_rule.nat_asg_hook.name
  target_id = "nat-asg-hook"
  arn       = aws_lambda_function.nat_asg_hook.arn
}

resource "aws_lambda_permission" "nat_asg_hook" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.nat_asg_hook.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.nat_asg_hook.arn
}
