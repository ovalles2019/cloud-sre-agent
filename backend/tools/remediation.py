"""Write actions — always gated by human approval."""

from __future__ import annotations

from typing import Any

import structlog

from backend.config import Settings

log = structlog.get_logger()


class RemediationTool:
    """Executes approved remediation actions against AWS APIs."""

    SUPPORTED = {
        "scale_ec2_asg": "Scale EC2 Auto Scaling Group desired capacity",
        "rightsize_ec2": "Stop underutilized EC2 instances flagged by TA",
        "increase_rds_capacity": "Modify RDS instance class or storage",
        "rollback_lambda": "Rollback Lambda alias to previous version",
        "create_budget_alert": "Create AWS Budget alert for service spend",
        "tune_alarm_threshold": "Update CloudWatch alarm threshold",
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def execute(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in self.SUPPORTED:
            return {"ok": False, "error": f"Unknown remediation action: {tool_name}"}

        if self.settings.demo_mode:
            log.info("demo_remediation_executed", tool=tool_name, parameters=parameters)
            return {
                "ok": True,
                "mode": "demo",
                "tool": tool_name,
                "message": f"Simulated execution of {tool_name}",
                "parameters": parameters,
                "aws_request_id": "demo-req-001",
            }

        return self._execute_live(tool_name, parameters)

    def _execute_live(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        import boto3

        region = self.settings.aws_region
        if tool_name == "scale_ec2_asg":
            asg = boto3.client("autoscaling", region_name=region)
            resp = asg.set_desired_capacity(
                AutoScalingGroupName=parameters["asg_name"],
                DesiredCapacity=int(parameters["desired_capacity"]),
            )
            return {"ok": True, "response_metadata": resp.get("ResponseMetadata", {})}

        if tool_name == "create_budget_alert":
            budgets = boto3.client("budgets", region_name=region)
            resp = budgets.create_budget(
                AccountId=parameters["account_id"],
                Budget=parameters["budget"],
                NotificationsWithSubscribers=parameters.get("notifications", []),
            )
            return {"ok": True, "response_metadata": resp.get("ResponseMetadata", {})}

        if tool_name == "tune_alarm_threshold":
            cw = boto3.client("cloudwatch", region_name=region)
            resp = cw.put_metric_alarm(**parameters["alarm_config"])
            return {"ok": True, "response_metadata": resp.get("ResponseMetadata", {})}

        return {"ok": False, "error": f"Live execution not implemented for {tool_name}"}
