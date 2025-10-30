import json
import logging
import os
import boto3
from botocore.config import Config

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def format_email_message(event, result):
    """Format the analysis result into a readable email message"""
    pipeline_name = result.get('pipeline_info', {}).get('name', 'Unknown')
    stage = result.get('pipeline_info', {}).get('stage', 'Unknown')
    
    # Extract solution from nested structure
    solution_body = result.get('solution_recommendations', {}).get('solution', {}).get('body', '')
    if solution_body.startswith('"') and solution_body.endswith('"'):
        solution_body = solution_body[1:-1]  # Remove quotes
    
    # Get pipeline failure status and error message from event
    pipeline_status = event.get('detail', {}).get('state', 'FAILED')
    error_message = event.get('detail', {}).get('execution-result', {}).get('external-execution-summary', 'No error details available')
    
    message = f"""
🚨 PIPELINE FAILURE ANALYSIS REPORT

📋 PIPELINE INFORMATION:
• Pipeline: {pipeline_name}
• Failed Stage: {stage}
• Pipeline Status: {pipeline_status}
• Analysis Status: {result.get('status', 'Unknown')}

🔍 ANALYSIS RESULT:
{solution_body.replace('\\n', '\n')}

📊 EVENT DETAILS:
• Source: {event.get('source', 'N/A')}
• Detail Type: {event.get('detail-type', 'N/A')}
• Time: {event.get('time', 'N/A')}
• Region: {event.get('region', 'N/A')}
• Error Message: {error_message}
"""
    return message

def call_agentcore_runtime(event):
    """Call Bedrock AgentCore runtime for pipeline analysis"""
    region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
    agent_arn = os.environ['AGENT_ARN']
    session_id = f"pipeline-analysis-{event.get('detail', {}).get('execution-id', 'unknown')}"
    
    config = Config(
        read_timeout=900,
        connect_timeout=60,
        retries={'max_attempts': 3}
    )
    
    agentcore_client = boto3.client('bedrock-agentcore', region_name=region, config=config)
    
    payload = {"event": event}
    
    response = agentcore_client.invoke_agent_runtime(
        agentRuntimeArn=agent_arn,
        runtimeSessionId=session_id,
        payload=json.dumps(payload).encode('utf-8')
    )

    if "text/event-stream" in response.get("contentType", ""):
        # Handle streaming response
        content = []
        for line in response["response"].iter_lines(chunk_size=10):
            if line:
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    line = line[6:]
                    print(line)
                    content.append(line)
        print("\nAgent response:", "\n".join(content))
        return json.loads("\n".join(content))

    elif response.get("contentType") == "application/json":
        # Handle standard JSON response
        content = []
        for chunk in response.get("response", []):
            content.append(chunk.decode('utf-8'))
        print("\nAgent response:")
        result = json.loads(''.join(content))
        print(result)
        return result
    
    else:
        # Print raw response for other content types
        print(f"Agent response: {response}")
        return response

##############################################################################
## Main Lambda Handler
##############################################################################
def lambda_handler(event, context):
    logger.info(f"Pipeline failure event received: {json.dumps(event, default=str)}")
    
    try:
        result = call_agentcore_runtime(event)
        region = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')
        
        # Send email notification
        sns_client = boto3.client('sns', region_name=region)
        topic_arn = os.environ['SNS_TOPIC_ARN']
        
        formatted_message = format_email_message(event, result)
        
        sns_client.publish(
            TopicArn=topic_arn,
            Subject=f"🚨 Pipeline Failure: {result.get('pipeline_info', {}).get('name', 'Unknown')}",
            Message=formatted_message
        )
        
        logger.info("Analysis completed successfully")
        return {
            "statusCode": 200, 
            "body": json.dumps(result, indent=2, default=str)
        }
        
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": "Pipeline analysis failed",
                "details": str(e)
            }, indent=2)
        }
