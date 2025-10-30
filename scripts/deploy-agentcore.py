#!/usr/bin/env python3
import subprocess
import boto3
import json
import os
import sys
import time
import base64

AGENT_IDS_FILE = 'scripts/agent_runtime_ids.json'

def wait_for_agent_ready(bedrock_client, agent_runtime_id):
    """Wait for agent to be in READY state"""
    print(f"Waiting for agent {agent_runtime_id} to be ready...")
    while True:
        response = bedrock_client.get_agent_runtime(agentRuntimeId=agent_runtime_id)
        status = response['status']
        print(f"Agent status: {status}")
        
        if status == 'READY':
            print("Agent is ready!")
            break
        elif status == 'FAILED':
            print("Agent deployment failed!")
            break
        
        time.sleep(10)

def load_agent_ids():
    if os.path.exists(AGENT_IDS_FILE):
        with open(AGENT_IDS_FILE, 'r') as f:
            return json.load(f)
    else:
        os.makedirs(AGENT_IDS_FILE, exist_ok=True)
    return {}

def save_agent_ids(agent_ids):
    with open(AGENT_IDS_FILE, 'w') as f:
        json.dump(agent_ids, f, indent=2)

def get_stack_outputs(stack_name):
    """Get CDK stack outputs"""
    cloudformation = boto3.client('cloudformation')
    response = cloudformation.describe_stacks(StackName=stack_name)
    outputs = {}
    for output in response['Stacks'][0].get('Outputs', []):
        outputs[output['OutputKey']] = output['OutputValue']
    return outputs

def build_and_push_image(ecr_uri):
    """Build and push Docker image to ECR"""
    # Get ECR login
    ecr_client = boto3.client('ecr')
    token = ecr_client.get_authorization_token()
    username, password = base64.b64decode(token['authorizationData'][0]['authorizationToken']).decode('utf-8').split(':')
    registry = token['authorizationData'][0]['proxyEndpoint']
    
    # Docker login
    subprocess.run([
        'docker', 'login', '--username', username, '--password-stdin', registry
    ], input=password.encode(), check=True)
    
    # Generate unique image tag using timestamp
    import time
    image_tag = str(int(time.time()))
    
    # Build image from root directory
    agent_path = './agent-container'
    
    subprocess.run([
        'docker', 'build', '--platform', 'linux/arm64', '--load', 
        '-t', f"{ecr_uri}:{image_tag}", agent_path
    ], check=True)
    
    # Push image
    subprocess.run([
        'docker', 'push', f"{ecr_uri}:{image_tag}"
    ], check=True)
    
    return f"{ecr_uri}:{image_tag}"

def deploy_agent(ecr_uri_with_tag, role_arn, secret_id):
    """Deploy Bedrock AgentCore"""
    bedrock_client = boto3.client('bedrock-agentcore-control')
    
    agent_ids = load_agent_ids()
    agent_name = 'pipeline_error_analysis_agent'
    
    env_vars = {
        'SECRET_ID': secret_id,
        'AWS_DEFAULT_REGION': boto3.Session().region_name or 'us-east-1'
    }
    
    deployment_params = {
        'agentRuntimeArtifact': {'containerConfiguration': {'containerUri': ecr_uri_with_tag}},
        'roleArn': role_arn,
        'networkConfiguration': {'networkMode': 'PUBLIC'},
        'protocolConfiguration': {'serverProtocol': 'HTTP'},
        'environmentVariables': env_vars
    }
    
    if agent_name in agent_ids:
        # Update existing agent
        try:
            bedrock_client.update_agent_runtime(
                agentRuntimeId=agent_ids[agent_name],
                **deployment_params
            )
            print(f"Updated agent: {agent_name}")
            wait_for_agent_ready(bedrock_client, agent_ids[agent_name])
        except Exception as e:
            print(f"Error updating {agent_name}: {e}")
    else:
        # Create new agent
        try:
            deployment_params['agentRuntimeName'] = agent_name
            response = bedrock_client.create_agent_runtime(**deployment_params)
            agent_ids[agent_name] = response['agentRuntimeId']
            print(f"Created agent: {agent_name} with ID: {response['agentRuntimeId']}")
            wait_for_agent_ready(bedrock_client, response['agentRuntimeId'])
        except Exception as e:
            print(f"Error creating {agent_name}: {e}")
    
    save_agent_ids(agent_ids)

if __name__ == "__main__":
    try:
        # Get stack outputs
        agentcore_outputs = get_stack_outputs('AgentCoreStack')
        secret_outputs = get_stack_outputs('SecretManagerStack')
        
        ecr_uri = agentcore_outputs['ECRRepositoryURI']
        role_arn = agentcore_outputs['AgentRoleArn']
        secret_id = secret_outputs['SecretId']
        
        print(f"ECR URI: {ecr_uri}")
        print(f"Role ARN: {role_arn}")
        print(f"Secret ID: {secret_id}")
        
        # Build and push image
        print("Building and pushing Docker image...")
        ecr_uri_with_tag = build_and_push_image(ecr_uri)
        
        # Deploy agent
        print("Deploying Bedrock AgentCore...")
        deploy_agent(ecr_uri_with_tag, role_arn, secret_id)
        
        print("Deployment completed successfully!")
        
    except Exception as e:
        print(f"Deployment failed: {e}")
        sys.exit(1)
