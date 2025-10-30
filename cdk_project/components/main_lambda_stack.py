from aws_cdk import Duration
from aws_cdk import Stack
from aws_cdk import aws_lambda as _lambda
from aws_cdk import aws_iam as iam
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_logs as logs
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subs
from aws_cdk import RemovalPolicy  # Add this import for CloudWatch Logs

from constructs import Construct

class MainLambdaStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, pipeline_name: str, config: dict, agent_arn: str = None, **kwargs,) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create SNS topic for email notifications
        notification_topic = sns.Topic(
            self,
            "PipelineNotificationTopic",
            topic_name="pipeline-error-notifications"
        )

        # Add email subscription to SNS topic
        for email in config["notification_emails"]:
            notification_topic.add_subscription(sns_subs.EmailSubscription(email))

        # Define the Lambda function resource first
        bedrock_lambda = _lambda.Function(
            self,
            "PipelineErrorAnalyzer",
            function_name="pipeline-error-analyzer",
            runtime=_lambda.Runtime.PYTHON_3_12,
            handler="error_handler.lambda_handler",
            code=_lambda.Code.from_asset("../lambda-code"),
            timeout=Duration.seconds(900),
            memory_size=1024,
            environment={
                "SNS_TOPIC_ARN": notification_topic.topic_arn,
                "AGENT_ARN": agent_arn
            }
        )

        # Create CloudWatch Log Group after Lambda is defined
        log_group = logs.LogGroup(
            self,
            "PipelineErrorAnalyzerLogGroup",
            log_group_name=f"/aws/lambda/{bedrock_lambda.function_name}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Add permissions to Lambda role (CDK automatically adds CloudWatch Logs permissions)
        bedrock_lambda.add_to_role_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sns:Publish"
                ],
                resources=["*"],
            )
        )
        bedrock_lambda.add_to_role_policy(
            iam.PolicyStatement(
                sid="BedrockAgentCoreRuntimeInvoke",
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock-agentcore:InvokeAgentRuntime"
                ],
                resources=[
                    f"{agent_arn}*"
                ]
            )
        )

        log_group = logs.LogGroup(
            self,
            f"CodePipelineLogGroup",
            log_group_name=f"/CodePipelineLogGroup/{pipeline_name}",
            retention=logs.RetentionDays.ONE_WEEK,
        )

        pipeline_failure_rule = events.Rule(
            self,
            "PipelineFailureRule",
            description=f"Captures CodePipeline failure events for {pipeline_name}",
            event_pattern=events.EventPattern(
                source=["aws.codepipeline"],
                detail_type=[
                    "CodePipeline Action Execution State Change",
                ],
                detail={"state": ["FAILED"], "pipeline": [pipeline_name]},
            ),
        )
        pipeline_failure_rule.add_target(targets.CloudWatchLogGroup(log_group))
        pipeline_failure_rule.add_target(targets.LambdaFunction(bedrock_lambda))
