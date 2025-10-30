import boto3

from aws_cdk import Stack
from aws_cdk import aws_logs as logs
from aws_cdk import aws_cloudtrail as cloudtrail
from constructs import Construct

from components.event_rule_stack import EventRuleStack
from components.ssm_parameter_stack import SsmParameterManager


class PipelineLoggerStack(Stack):
    def __init__(
        self, scope: Construct, id: str, pipeline_name: str, stages: list, **kwargs
    ):
        super().__init__(scope, id, **kwargs)

        # Create CloudTrail
        self.trail = cloudtrail.Trail(
            self,
            "SharedPipelineTrail",
            is_multi_region_trail=True,
            send_to_cloud_watch_logs=True,
            cloud_watch_log_group=logs.LogGroup(
                self, "SolutionTrailLogGroup", retention=logs.RetentionDays.ONE_MONTH
            ),
        )

        for stage in stages:
            provider = stage["provider"]
            config = stage["configuration"]
            stage_name = stage["stage_name"]
            action_name = stage["action_name"]

            log_group_name = (
                f"/codepipeline/{pipeline_name}/{stage_name}/{action_name}/{provider}"
            )

            if provider == "S3":
                bucket_name = config.get("S3Bucket")
                if bucket_name:
                    log_group_name += f"/{bucket_name}"
                    EventRuleStack.create_event_rule_for_s3(
                        stage_name,
                        action_name,
                        bucket_name,
                        log_group_name,
                        self.trail,
                        self,
                        None,
                    )
                    SsmParameterManager(
                        self,
                        f"S3LogParam{stage_name}{action_name}",
                        f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/s3-event-log-group",
                        log_group_name,
                    )

            elif provider == "ECR":
                repository_name = config.get("RepositoryName")
                if repository_name:
                    log_group_name += f"/{repository_name}"
                    EventRuleStack.create_event_rule_for_ecr(
                        stage_name,
                        action_name,
                        repository_name,
                        log_group_name,
                        self,
                        None,
                    )
                    SsmParameterManager(
                        self,
                        f"ECRLogParam{stage_name}{action_name}",
                        f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/ecr-event-log-group",
                        log_group_name,
                    )

            elif provider == "CodeBuild":
                project_name = config.get("ProjectName")
                if project_name:
                    log_group_name += f"/{project_name}"
                    EventRuleStack.create_event_rule_for_codebuild(
                        stage_name,
                        action_name,
                        project_name,
                        log_group_name,
                        self,
                        None,
                    )

                    # Create SSM parameter for event log group
                    SsmParameterManager(
                        self,
                        f"CodeBuildEventLogParam{stage_name}{action_name}",
                        f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/codebuild-event-log-group",
                        log_group_name,
                    )

                    # Get actual CodeBuild log group using boto3
                    try:
                        client = boto3.client("codebuild")
                        response = client.batch_get_projects(names=[project_name])

                        if response["projects"]:
                            project = response["projects"][0]
                            logs_config = project.get("logsConfig", {})
                            cloudwatch_logs = logs_config.get("cloudWatchLogs", {})
                            actual_log_group = (cloudwatch_logs.get("groupName") or f"/aws/codebuild/{project_name}")
                        else:
                            print(
                                f"No project found with name: {project_name}, using default"
                            )
                            actual_log_group = f"/aws/codebuild/{project_name}"
                    except Exception as e:
                        print(
                            f"Error fetching CodeBuild project {project_name}: {e}, using default"
                        )
                        actual_log_group = f"/aws/codebuild/{project_name}"

                    # Create SSM parameter for actual CodeBuild log group
                    SsmParameterManager(
                        self,
                        f"CodeBuildNativeLogParam{stage_name}{action_name}",
                        f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/codebuild-native-log-group",
                        actual_log_group,
                    )

            elif provider == "CloudFormation":
                stack_name = config.get("StackName")
                if stack_name:
                    log_group_name += f"/{stack_name}"
                    EventRuleStack.create_event_rule_for_cloudformation(
                        stage_name, action_name, stack_name, log_group_name, self, None
                    )
                    SsmParameterManager(
                        self,
                        f"CFNLogParam{stage_name}{action_name}",
                        f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/cfn-event-log-group",
                        log_group_name,
                    )

            elif provider == "CodeStarSourceConnection":
                SsmParameterManager(
                    self,
                    f"SourceLogParam{stage_name}{action_name}",
                    f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/source-event-log-group",
                    log_group_name,
                )
