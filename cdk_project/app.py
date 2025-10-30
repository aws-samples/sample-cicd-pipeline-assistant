import json
import yaml
import aws_cdk as cdk

from components.pipeline_logger_stack import PipelineLoggerStack
from components.main_lambda_stack import MainLambdaStack
from components.secret_manager_stack import SecretManagerStack
from components.agentcore_stack import AgentCoreStack

with open("../pipeline_config/stages.json") as f:
    data = json.load(f)

with open("../email-config/config.yaml") as f:
    config = yaml.safe_load(f)

app = cdk.App()

# Create Logger Stack
pipeline_logger_stack = PipelineLoggerStack(app, "PipelineLoggerStack", pipeline_name=data["pipeline_name"], stages=data["stages"])

# Create secret Stack
secret_stack = SecretManagerStack(app, "SecretManagerStack")

# Create AgentCore stack
agentcore_stack = AgentCoreStack(app, "AgentCoreStack", config=config)

# Create Lambda stack (only if agent_arn context is provided)
agent_arn = app.node.try_get_context("agent_arn")
if agent_arn:
    MainLambdaStack(
        app, "MainLambdaStack",
        pipeline_name=data["pipeline_name"],
        config=config,
        agent_arn=agent_arn
    )

app.synth()
