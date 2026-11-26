# Alerts go to the same email as the budget alarms. AWS emails a confirmation link
# the first time: the subscription stays "pending" until you click it.
resource "aws_sns_topic" "alerts" {
  name_prefix = "${var.project_tag}-alerts-"
}

resource "aws_sns_topic_subscription" "email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Host failure (hardware): EC2 moves the instance to healthy hardware, same disk and IP.
resource "aws_cloudwatch_metric_alarm" "status_system" {
  alarm_name          = "${var.project_tag}-status-check-system"
  alarm_description   = "AWS reports a problem with the underlying host; auto-recover and notify."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 60
  evaluation_periods  = 2
  treat_missing_data  = "breaching"

  dimensions = { InstanceId = aws_instance.kiwi.id }

  alarm_actions = [
    aws_sns_topic.alerts.arn,
    "arn:aws:automate:${var.region}:ec2:recover",
  ]
}

# OS-level failure (kernel panic, out of memory, broken networking): notify only.
resource "aws_cloudwatch_metric_alarm" "status_instance" {
  alarm_name          = "${var.project_tag}-status-check-instance"
  alarm_description   = "The VM's operating system is not responding to health checks."
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_Instance"
  statistic           = "Maximum"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  period              = 60
  evaluation_periods  = 3
  treat_missing_data  = "breaching"

  dimensions = { InstanceId = aws_instance.kiwi.id }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

# t3 instances throttle to a baseline when CPU credits run out: the site gets very slow.
resource "aws_cloudwatch_metric_alarm" "cpu_credits" {
  alarm_name          = "${var.project_tag}-cpu-credits-low"
  alarm_description   = "CPU credit balance is nearly empty; the VM will be throttled."
  namespace           = "AWS/EC2"
  metric_name         = "CPUCreditBalance"
  statistic           = "Minimum"
  comparison_operator = "LessThanThreshold"
  threshold           = 20
  period              = 300
  evaluation_periods  = 3
  treat_missing_data  = "notBreaching"

  dimensions = { InstanceId = aws_instance.kiwi.id }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}

resource "aws_cloudwatch_metric_alarm" "cpu_high" {
  alarm_name          = "${var.project_tag}-cpu-high"
  alarm_description   = "CPU above 90% for 30 minutes."
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  comparison_operator = "GreaterThanThreshold"
  threshold           = 90
  period              = 300
  evaluation_periods  = 6
  treat_missing_data  = "notBreaching"

  dimensions = { InstanceId = aws_instance.kiwi.id }

  alarm_actions = [aws_sns_topic.alerts.arn]
  ok_actions    = [aws_sns_topic.alerts.arn]
}
