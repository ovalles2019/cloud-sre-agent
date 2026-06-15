#!/usr/bin/env python3
"""AWS CDK stack for Cloud SRE Agent infrastructure."""

from aws_cdk import (
    App,
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
)
from constructs import Construct


class CloudSreAgentStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        incidents = dynamodb.Table(
            self,
            "IncidentsTable",
            table_name="cloud-sre-incidents",
            partition_key=dynamodb.Attribute(name="incident_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        approvals = dynamodb.Table(
            self,
            "ApprovalsTable",
            table_name="cloud-sre-approvals",
            partition_key=dynamodb.Attribute(name="approval_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        action_fn = lambda_.Function(
            self,
            "ActionGroupHandler",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset("../lambdas/action_groups"),
            timeout=Duration.seconds(30),
            environment={
                "APPROVALS_TABLE": approvals.table_name,
            },
            log_retention=logs.RetentionDays.ONE_WEEK,
        )

        action_fn.add_to_role_policy(
            iam.PolicyStatement(
                actions=[
                    "cloudwatch:DescribeAlarms",
                    "cloudwatch:GetMetricStatistics",
                    "ce:GetCostAndUsage",
                    "support:DescribeTrustedAdvisorChecks",
                    "support:DescribeTrustedAdvisorCheckResult",
                    "autoscaling:SetDesiredCapacity",
                    "lambda:UpdateAlias",
                    "budgets:CreateBudget",
                ],
                resources=["*"],
            )
        )
        approvals.grant_read_write_data(action_fn)

        api = apigw.RestApi(
            self,
            "CloudSreAgentApi",
            rest_api_name="cloud-sre-agent",
            description="Action groups API for Bedrock Agent",
        )
        proxy = api.root.add_resource("{proxy+}")
        proxy.add_method("ANY", apigw.LambdaIntegration(action_fn))

        bedrock_role = iam.Role(
            self,
            "BedrockAgentRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
        )
        bedrock_role.add_to_policy(
            iam.PolicyStatement(
                actions=["lambda:InvokeFunction"],
                resources=[action_fn.function_arn],
            )
        )

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "ActionGroupLambdaArn", value=action_fn.function_arn)
        CfnOutput(self, "IncidentsTableName", value=incidents.table_name)
        CfnOutput(self, "ApprovalsTableName", value=approvals.table_name)
        CfnOutput(self, "BedrockAgentRoleArn", value=bedrock_role.role_arn)


app = App()
CloudSreAgentStack(app, "CloudSreAgentStack")
app.synth()
