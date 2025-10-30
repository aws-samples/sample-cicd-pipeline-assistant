# #!/bin/bash
# set -e

# echo "Get Pipeline Config"
# python3 scripts/get-pipeline-config.py --pipeline-name=cicd_assistant_pipeline --region=us-east-1

# echo "1. Deploy Secret and AgentCore stacks..."
# cd cdk_project
# cdk deploy SecretManagerStack AgentCoreStack

# echo "2. Deploy AgentCore container..."
# cd ..
# python3 scripts/deploy-agentcore.py

# echo "3. Get Agent ARN..."
# AGENT_ARN=$(python3 -c "
# import boto3, json
# with open('scripts/agent_runtime_ids.json', 'r') as f:
#     agent_ids = json.load(f)
# agent_id = list(agent_ids.values())[0]
# region = boto3.Session().region_name or 'us-east-1'
# account = boto3.client('sts').get_caller_identity()['Account']
# print(f'arn:aws:bedrock-agentcore:{region}:{account}:runtime/{agent_id}')
# ")

# echo "4. Deploy Lambda stack with Agent ARN..."
# cd cdk_project
# cdk deploy MainLambdaStack --context agent_arn="$AGENT_ARN"

# echo "Deployment complete!"


#!/bin/bash

# Exit on any error
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to log messages
log_info() {
    printf "${GREEN}[INFO]${NC} %s\n" "$1"
}

log_error() {
    printf "${RED}[ERROR]${NC} %s\n" "$1" >&2
}

log_prompt() {
    printf "${BLUE}[INPUT]${NC} %s\n" "$1"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to prompt for input with validation
prompt_input() {
    local prompt_message="$1"
    local variable_name="$2"
    local input_value=""
    
    while [[ -z "$input_value" ]]; do
        log_prompt "$prompt_message"
        read -r input_value
        if [[ -z "$input_value" ]]; then
            log_error "This field cannot be empty. Please try again."
        fi
    done
    
    eval "$variable_name='$input_value'"
}

# Welcome message
printf "${GREEN}===========================================${NC}\n"
printf "${GREEN}    CICD Pipeline Assistant Deployment     ${NC}\n"
printf "${GREEN}===========================================${NC}\n"
printf "\n"

# Check prerequisites
log_info "Checking prerequisites..."

if ! command_exists python3; then
    log_error "python3 is not installed or not in PATH"
    exit 1
fi

if ! command_exists aws; then
    log_error "AWS CLI is not installed or not in PATH"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS credentials not configured. Please run 'aws configure' first"
    exit 1
fi

# Check if required files exist
if [[ ! -f "scripts/get-pipeline-config.py" ]]; then
    log_error "scripts/get-pipeline-config.py not found"
    exit 1
fi

log_info "Prerequisites check passed!"
printf "\n"

# Prompt for pipeline name and region
prompt_input "Enter the pipeline name:" PIPELINE_NAME
prompt_input "Enter the AWS region (e.g., us-east-1, eu-west-1):" REGION

printf "\n"
log_info "Configuration Summary:"
printf "  Pipeline Name: %s\n" "$PIPELINE_NAME"
printf "  Region: %s\n" "$REGION"
printf "\n"

# Confirm before proceeding
log_prompt "Do you want to proceed with the deployment? (Y/N):"
read -r confirm
if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
    log_info "Deployment cancelled by user"
    exit 0
fi

printf "\n"
log_info "Starting deployment process..."

# Step 1: Get Pipeline Config
log_info "Step 1: Getting pipeline configuration..."
if ! python3 scripts/get-pipeline-config.py --pipeline-name="$PIPELINE_NAME" --region="$REGION"; then
    log_error "Failed to get pipeline configuration"
    exit 1
fi

# Step 2: Deploy Pipeline-logger Secret and AgentCore stacks
log_info "Step 2: Deploying Pipeline-logger, Secret and AgentCore stacks..."
if ! (cd cdk_project && cdk ls && cdk deploy PipelineLoggerStack SecretManagerStack AgentCoreStack --region="$REGION"); then
    log_error "Failed to deploy Secret and AgentCore stacks"
    exit 1
fi

# Step 3: Deploy AgentCore container
log_info "Step 3: Deploying AgentCore container..."
if ! python3 scripts/deploy-agentcore.py; then
    log_error "Failed to deploy AgentCore container"
    exit 1
fi

# Step 4: Get Agent ARN
log_info "Step 4: Getting Agent ARN..."
AGENT_ARN=$(python3 -c "
import boto3, json, sys
try:
    with open('scripts/agent_runtime_ids.json', 'r') as f:
        agent_ids = json.load(f)
    agent_id = list(agent_ids.values())[0]
    account = boto3.client('sts', region_name='$REGION').get_caller_identity()['Account']
    print(f'arn:aws:bedrock-agentcore:$REGION:{account}:runtime/{agent_id}')
except Exception as e:
    print(f'Error: {e}', file=sys.stderr)
    sys.exit(1)
")

if [[ -z "$AGENT_ARN" ]]; then
    log_error "Failed to get Agent ARN"
    exit 1
fi

log_info "Agent ARN: $AGENT_ARN"

# Step 5: Deploy Lambda stack
log_info "Step 5: Deploying Lambda stack with Agent ARN..."
if ! (cd cdk_project && cdk ls && cdk deploy MainLambdaStack --context agent_arn="$AGENT_ARN" --region="$REGION"); then
    log_error "Failed to deploy Lambda stack"
    exit 1
fi

printf "\n"
log_info "Deployment completed successfully!"