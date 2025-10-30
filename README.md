# CICD-PIPELINE ASSISTANT

A CDK Python project that helps analyze and fix CI/CD pipeline failures using AWS Bedrock.

## Overview

This project deploys AWS resources that monitor your CodePipeline for failures, analyze error messages using Amazon Bedrock, and provide solutions using AI for common pipeline issues.

## Getting Started

### Prerequisites

- AWS CLI configured
- Python 3.x

### Installation

1. **Clone the Repository**

2. **Navigate to the Project Directory**

   ```bash
   cd CICD-PIPELINE-ASSISTANT
   ```

3. **Create a Virtual Environment**

   ```bash
   python3 -m venv .venv
   ```

4. **Activate the Virtual Environment**

   On MacOS/Linux:

   ```bash
   source .venv/bin/activate
   ```

   On Windows:

   ```bash
   .venv\Scripts\activate.bat
   ```

5. **Install Dependencies**

   ```bash
   pip install -r requirements.txt
   ```

## Deployment

0. **Configure your aws account connectivity from you shell**

   ```bash
   aws configure
   ```

1. **Run following file for the deployment**

   ```bash
   ./scripts/deploy.sh
   ```

## Adding Github access token to SecretManager

Add this as plain text in the 'github-credentials' secret created for you while you deploy the stack.

   ```text
      {"access_token":"<Your_Github_Token>","repo_url":"<https://github.com/><YOUR_USERNAME>/<REPO_NAME>.git"}
   ```

## Cleanup Resources

   ```bash
   ./scripts/cleanup.sh
   ```

## Useful Commands

- `cdk ls` - List all stacks in the app also checks for the error
- `cdk synth` - Emit the synthesized CloudFormation template
- `cdk deploy` - Deploy this stack to your default AWS account/region
- `cdk diff` - Compare deployed stack with current state
- `cdk docs` - Open CDK documentation

## License

This project is licensed under the MIT License - see the LICENSE file for details.
