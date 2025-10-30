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

log_warning() {
    printf "${YELLOW}[WARNING]${NC} %s\n" "$1"
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

# Function to clean ECR repository completely
clean_ecr_repository() {
    local repo_name="$1"
    local region="$2"
    
    log_info "Cleaning ECR repository: $repo_name"
    
    # Check if repository exists
    if ! aws ecr describe-repositories --repository-names "$repo_name" --region="$region" >/dev/null 2>&1; then
        log_warning "ECR repository $repo_name not found"
        return 0
    fi
    
    # Simple approach: use AWS CLI to delete repository with force flag
    log_info "Force deleting ECR repository with all images..."
    
    if aws ecr delete-repository --repository-name "$repo_name" --region="$region" --force >/dev/null 2>&1; then
        log_info "ECR repository $repo_name deleted successfully"
        return 0
    else
        log_warning "Force delete failed, trying manual image cleanup..."
        
        # Fallback: try to delete images manually first
        local temp_file=$(mktemp)
        aws ecr list-images --repository-name "$repo_name" --region="$region" --query 'imageIds' --output json > "$temp_file" 2>/dev/null || echo "[]" > "$temp_file"
        
        # Use Python to read the temp file and delete images
        python3 -c "
import boto3
import json
import sys

try:
    with open('$temp_file', 'r') as f:
        image_ids = json.load(f)
    
    if image_ids:
        ecr_client = boto3.client('ecr', region_name='$region')
        print(f'Found {len(image_ids)} images to delete')
        
        # Delete images in batches of 100
        batch_size = 100
        for i in range(0, len(image_ids), batch_size):
            batch = image_ids[i:i + batch_size]
            try:
                response = ecr_client.batch_delete_image(
                    repositoryName='$repo_name',
                    imageIds=batch
                )
                deleted_count = len(response.get('imageIds', []))
                print(f'Deleted {deleted_count} images')
            except Exception as e:
                print(f'Error deleting batch: {e}')
        
        print('Image cleanup completed')
    else:
        print('No images found')
        
except Exception as e:
    print(f'Error: {e}')
    sys.exit(1)
"
        
        rm -f "$temp_file"
        
        # Try to delete repository again after cleaning images
        if aws ecr delete-repository --repository-name "$repo_name" --region="$region" >/dev/null 2>&1; then
            log_info "ECR repository $repo_name deleted successfully after image cleanup"
            return 0
        else
            log_error "Failed to delete ECR repository $repo_name"
            return 1
        fi
    fi
}

# Welcome message
printf "${RED}===========================================${NC}\n"
printf "${RED}    CICD Pipeline Assistant CLEANUP       ${NC}\n"
printf "${RED}===========================================${NC}\n"
printf "\n"

log_warning "This script will DELETE ALL resources created by the deployment!"
log_warning "This action is IRREVERSIBLE!"
printf "\n"

# Check prerequisites
log_info "Checking prerequisites..."

if ! command_exists aws; then
    log_error "AWS CLI is not installed or not in PATH"
    exit 1
fi

if ! command_exists python3; then
    log_error "python3 is not installed or not in PATH"
    exit 1
fi

# Check if AWS credentials are configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    log_error "AWS credentials not configured. Please run 'aws configure' first"
    exit 1
fi

log_info "Prerequisites check passed!"
printf "\n"

# Prompt for region
prompt_input "Enter the AWS region where resources were deployed:" REGION

printf "\n"
log_info "Configuration Summary:"
printf "  Region: %s\n" "$REGION"
printf "\n"

# Final confirmation
log_warning "You are about to DELETE the following resources:"
printf "  - Lambda functions and stacks\n"
printf "  - AgentCore containers and stacks\n"
printf "  - ECR repositories and images\n"
printf "  - Secret Manager stacks\n"
printf "  - All associated AWS resources\n"
printf "\n"

log_prompt "Are you ABSOLUTELY SURE you want to proceed? Type 'DELETE' to confirm:"
read -r confirm
if [[ "$confirm" != "DELETE" ]]; then
    log_info "Cleanup cancelled by user"
    exit 0
fi

printf "\n"
log_info "Starting cleanup process..."

# Step 1: Destroy Lambda stack
log_info "Step 1: Destroying Lambda stack..."
if (cd cdk_project && cdk destroy MainLambdaStack --region="$REGION" --force); then
    log_info "Lambda stack destroyed successfully"
else
    log_warning "Failed to destroy Lambda stack or stack doesn't exist"
fi

# Step 2: Clean up AgentCore containers
log_info "Step 2: Cleaning up AgentCore containers..."
if [[ -f "scripts/agent_runtime_ids.json" ]]; then
    python3 -c "
import boto3, json, sys
try:
    with open('scripts/agent_runtime_ids.json', 'r') as f:
        agent_ids = json.load(f)
    
    client = boto3.client('bedrock-agentcore', region_name='$REGION')
    for agent_id in agent_ids.values():
        try:
            client.delete_runtime(runtimeId=agent_id)
            print(f'Deleted AgentCore runtime: {agent_id}')
        except Exception as e:
            print(f'Failed to delete runtime {agent_id}: {e}')
except Exception as e:
    print(f'Error cleaning up AgentCore: {e}')
" || log_warning "Failed to clean up AgentCore containers"
else
    log_warning "agent_runtime_ids.json not found, skipping AgentCore cleanup"
fi

# Step 3: Clean ECR repositories
log_info "Step 3: Cleaning ECR repositories..."
clean_ecr_repository "pipeline-agent" "$REGION"

# Step 4: Destroy AgentCore and Secret stacks
log_info "Step 4: Destroying AgentCore and Secret stacks..."
if (cd cdk_project && cdk destroy AgentCoreStack --region="$REGION" --force); then
    log_info "AgentCore stack destroyed successfully"
else
    log_warning "Failed to destroy AgentCore stack"
fi

if (cd cdk_project && cdk destroy SecretManagerStack --region="$REGION" --force); then
    log_info "Secret Manager stack destroyed successfully"
else
    log_warning "Failed to destroy Secret Manager stack or stack doesn't exist"
fi

# Step 5: Clean up local files
log_info "Step 5: Cleaning up local configuration files..."
if [[ -f "scripts/agent_runtime_ids.json" ]]; then
    rm -f "scripts/agent_runtime_ids.json"
    log_info "Removed agent_runtime_ids.json"
fi

if [[ -d "cdk_project/pipeline_config" ]]; then
    rm -rf "cdk_project/pipeline_config"
    log_info "Removed pipeline_config directory"
fi

# Step 6: List any remaining resources
log_info "Step 6: Checking for any remaining resources..."
printf "\n"
log_info "Checking CloudFormation stacks in region $REGION:"
aws cloudformation list-stacks --region="$REGION" --stack-status-filter CREATE_COMPLETE UPDATE_COMPLETE DELETE_FAILED --query 'StackSummaries[?contains(StackName, `SecretManager`) || contains(StackName, `AgentCore`) || contains(StackName, `MainLambda`)].{Name:StackName,Status:StackStatus}' --output table || true

printf "\n"
log_info "Cleanup completed!"
log_warning "Please verify in AWS Console that all resources have been removed"
