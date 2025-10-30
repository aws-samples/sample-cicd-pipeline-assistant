from aws_cdk import aws_ssm as ssm
from constructs import Construct

class SsmParameterManager(Construct):
    def __init__(self, scope: Construct, construct_id: str, parameter_name: str, log_group_name: str):
        super().__init__(scope, construct_id)
        
        try:
            self.parameter = ssm.StringParameter(
                self,
                "LogGroupParam",
                parameter_name=parameter_name,
                string_value=log_group_name,
            )
        except Exception as e:
            print(f"Error creating SSM parameter {parameter_name}: {str(e)}")
            self.parameter = None
