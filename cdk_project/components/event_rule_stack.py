from aws_cdk import Stack
from aws_cdk import aws_logs as logs
from aws_cdk import aws_events as events
from aws_cdk import aws_events_targets as targets
from aws_cdk import aws_cloudtrail as cloudtrail
from aws_cdk import aws_s3 as s3

from constructs import Construct


class EventRuleStack(Stack):
    def __init__(self, scope: Construct, id: str):
        super().__init__(scope, id)

    ##############################################################################
    ## Create Event Rule For S3
    ##############################################################################
    @staticmethod
    def create_event_rule_for_s3(
        stage_name: str,
        action_name: str,
        bucket_name: str,
        log_group_name: str,
        trail: cloudtrail,
        stack: Stack,
        log_group_manager=None,
    ):
        bucket = s3.Bucket.from_bucket_name(
            stack, f"{stage_name}{action_name}Bucket", bucket_name
        )

        trail.add_s3_event_selector(
            [cloudtrail.S3EventSelector(bucket=bucket, object_prefix="")],
            read_write_type=cloudtrail.ReadWriteType.ALL,
        )

        log_group = logs.LogGroup(
            stack,
            f"{stage_name}{action_name}S3LogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        if log_group_manager:
            log_group_manager.add_log_group(log_group_name)

        rule = events.Rule(
            stack,
            f"{stage_name}{action_name}S3EventRule",
            event_pattern=events.EventPattern(
                source=["aws.s3"],
                detail_type=["AWS API Call via CloudTrail"],
                detail={
                    "eventSource": ["s3.amazonaws.com"],
                    "requestParameters": {"bucketName": [bucket_name]},
                },
            ),
        )

        rule.add_target(targets.CloudWatchLogGroup(log_group))
        return log_group, rule

    ##############################################################################
    ## Create Event Rule For ECR
    ##############################################################################
    @staticmethod
    def create_event_rule_for_ecr(
        stage_name: str,
        action_name: str,
        repository_name: str,
        log_group_name: str,
        stack: Stack,
        log_group_manager=None,
    ):
        log_group = logs.LogGroup(
            stack,
            f"{stage_name}{action_name}ECRLogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        if log_group_manager:
            log_group_manager.add_log_group(log_group_name)

        rule = events.Rule(
            stack,
            f"{stage_name}{action_name}ECREventRule",
            event_pattern=events.EventPattern(
                source=["aws.ecr"],
                detail_type=["ECR Image Action"],
                detail={
                    "repository-name": [repository_name],
                },
            ),
        )
        rule.add_target(targets.CloudWatchLogGroup(log_group))
        return log_group, rule

    ##############################################################################
    ## Create Event Rule For CODEBUILD
    ##############################################################################
    @staticmethod
    def create_event_rule_for_codebuild(
        stage_name: str,
        action_name: str,
        codebuild_project_name: str,
        log_group_name: str,
        stack: Stack,
        log_group_manager=None,
    ):
        log_group = logs.LogGroup(
            stack,
            f"{stage_name}{action_name}CodeBuildLogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        if log_group_manager:
            log_group_manager.add_log_group(log_group_name)

        rule = events.Rule(
            stack,
            f"{stage_name}{action_name}CodeBuildEventRule",
            event_pattern=events.EventPattern(
                source=["aws.codebuild"],
                detail_type=["CodeBuild Build State Change"],
                detail={"project-name": [codebuild_project_name]},
            ),
        )

        rule.add_target(targets.CloudWatchLogGroup(log_group))
        return log_group, rule

    ##############################################################################
    ## Create Event Rule For cfn
    ##############################################################################
    @staticmethod
    def create_event_rule_for_cloudformation(
        stage_name: str,
        action_name: str,
        stack_name: str,
        log_group_name: str,
        stack: Stack,
        log_group_manager=None,
    ):
        log_group = logs.LogGroup(
            stack,
            f"{stage_name}{action_name}CloudFormationLogGroup",
            log_group_name=log_group_name,
            retention=logs.RetentionDays.ONE_WEEK,
        )

        if log_group_manager:
            log_group_manager.add_log_group(log_group_name)

        account_id = Stack.of(stack).account
        region = Stack.of(stack).region

        resource_prefix = (
            f"arn:aws:cloudformation:{region}:{account_id}:stack/{stack_name}/"
        )

        rule = events.Rule(
            stack,
            f"{stage_name}{action_name}CloudFormationEventRule",
            event_pattern=events.EventPattern(
                source=["aws.cloudformation"],
                detail_type=[
                    "CloudFormation Resource Status Change",
                    "CloudFormation Stack Status Change",
                ],
                resources=[f"events.Match.prefix(resource_prefix)"],
            ),
        )

        rule.add_target(targets.CloudWatchLogGroup(log_group))
        return log_group, rule
