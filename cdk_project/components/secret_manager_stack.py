from aws_cdk import Stack, CfnOutput
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import RemovalPolicy

from constructs import Construct


class SecretManagerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # GitHub credentials secret
        github_secret = secretsmanager.Secret(
            self,
            "GitHubCredentials",
            secret_name="github-credentials",
            description="GitHub access token and repository URL",
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Expose the Secret properties
        self.secret_arn = github_secret.secret_arn
        self.secret_id = github_secret.secret_name
        
        # Output for deployment script
        CfnOutput(self, "SecretId", value=self.secret_id)