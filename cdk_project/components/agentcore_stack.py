from aws_cdk import Stack, RemovalPolicy, CfnOutput
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_iam as iam
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as sns_subs
from constructs import Construct

class AgentCoreStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Create ECR repository for the agent container
        self.ecr_repository = ecr.Repository(
            self,
            "PipelineAgentRepository",
            repository_name="pipeline-agent",
            removal_policy=RemovalPolicy.DESTROY,
            image_scan_on_push=True
        )

        # Create IAM role for Bedrock AgentCore with proper permissions
        self.agent_role = iam.Role(
            self,
            "BedrockAgentRole",
            role_name="BedrockAgent-pipeline-agent-Role",
            assumed_by=iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
            inline_policies={
                "BedrockAgentPolicy": iam.PolicyDocument(
                    statements=[
                        # ECR Access
                        iam.PolicyStatement(
                            sid="ECRImageAccess",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ecr:BatchGetImage",
                                "ecr:GetDownloadUrlForLayer"
                            ],
                            resources=[f"arn:aws:ecr:{self.region}:{self.account}:repository/*"]
                        ),
                        iam.PolicyStatement(
                            sid="ECRTokenAccess",
                            effect=iam.Effect.ALLOW,
                            actions=["ecr:GetAuthorizationToken"],
                            resources=["*"]
                        ),
                        # CloudWatch Logs
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:DescribeLogStreams",
                                "logs:CreateLogGroup"
                            ],
                            resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["logs:DescribeLogGroups"],
                            resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "logs:CreateLogStream",
                                "logs:PutLogEvents"
                            ],
                            resources=[
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/bedrock-agentcore/runtimes/*:log-stream:*",
                                f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/vendedlogs/bedrock-agentcore/*:log-stream:*"
                            ]
                        ),
                        # X-Ray and CloudWatch
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "xray:PutTraceSegments",
                                "xray:PutTelemetryRecords",
                                "xray:GetSamplingRules",
                                "xray:GetSamplingTargets"
                            ],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=["cloudwatch:PutMetricData"],
                            resources=["*"],
                            conditions={
                                "StringEquals": {
                                    "cloudwatch:namespace": "bedrock-agentcore"
                                }
                            }
                        ),
                        # Bedrock AgentCore Access
                        iam.PolicyStatement(
                            sid="GetAgentAccessToken",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock-agentcore:GetWorkloadAccessToken",
                                "bedrock-agentcore:GetWorkloadAccessTokenForJWT",
                                "bedrock-agentcore:GetWorkloadAccessTokenForUserId"
                            ],
                            resources=[
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default",
                                f"arn:aws:bedrock-agentcore:{self.region}:{self.account}:workload-identity-directory/default/workload-identity/*"
                            ]
                        ),
                        # Bedrock Model Access
                        iam.PolicyStatement(
                            sid="BedrockModelInvocation",
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:InvokeModel",
                                "bedrock:InvokeModelWithResponseStream",
                                "bedrock:GetInferenceProfile"
                            ],
                            resources=[
                                "arn:aws:bedrock:*::foundation-model/*",
                                f"arn:aws:bedrock:{self.region}:{self.account}:*"
                            ]
                        ),
                        # Application specific permissions
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "codepipeline:GetPipeline",
                                "codepipeline:ListPipelineExecutions",
                                "codepipeline:GetPipelineExecution",
                                "logs:FilterLogEvents",
                                "secretsmanager:GetSecretValue",
                                "ssm:GetParameter"
                            ],
                            resources=["*"]
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "bedrock:ListFoundationModels",
                                "logs:DescribeLogGroups", 
                                "logs:DescribeLogStreams",
                                "logs:FilterLogEvents",
                                "logs:GetLogEvents",
                                "codepipeline:ListPipelineExecutions",
                                "codepipeline:GetPipelineExecution",
                            ],
                            resources=["*"],
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "secretsmanager:GetSecretValue"
                            ],
                            resources=["arn:aws:secretsmanager:*:*:secret:github-credentials*"],
                        ),
                        iam.PolicyStatement(
                            effect=iam.Effect.ALLOW,
                            actions=[
                                "ssm:GetParameter", 
                                "ssm:GetParameters"
                            ],
                            resources=["arn:aws:ssm:*:*:parameter/pipeline/*"],
                        )
                    ]
                )
            }
        )

        # Outputs for deployment script
        CfnOutput(self, "ECRRepositoryURI", value=self.ecr_repository.repository_uri)
        CfnOutput(self, "AgentRoleArn", value=self.agent_role.role_arn)

    @property
    def ecr_uri(self):
        return self.ecr_repository.repository_uri

    @property
    def role_arn(self):
        return self.agent_role.role_arn

    @property
    def sns_topic_arn(self):
        return self.notification_topic.topic_arn
