import os
import boto3
import logging
from typing import Dict, Any
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from repo_structure_function import handle_repo_structure
from solution_provider_function import handle_solution_provider
from log_analysis_function import handle_log_analysis

logger = logging.getLogger()
logger.setLevel(logging.INFO)

app = BedrockAgentCoreApp()

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

##############################################################################
## Extract Error Info From the Event
##############################################################################
def _extract_error_info(event: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "pipeline_name": event.get("detail", {}).get("pipeline", ""),
        "stage": event.get("detail", {}).get("stage", ""),
        "action": event.get("detail", {}).get("action-name", ""),
        "timestamp": event.get("time", ""),
        "error_code": event.get("detail", {})
        .get("execution-result", {})
        .get("error-code", ""),
        "error_summary": event.get("detail", {})
        .get("execution-result", {})
        .get("external-execution-summary", ""),
    }

##############################################################################
## Get Branch Name From Source
##############################################################################
def get_pipeline_source_branch(pipeline_event: Dict[str, Any]) -> str:
    client = boto3.client("codepipeline", region_name=AWS_DEFAULT_REGION)
    try:
        pipeline_name = pipeline_event.get("detail", {}).get("pipeline")
        if not pipeline_name:
            raise ValueError("Pipeline name not found in event")
        response = client.get_pipeline(name=pipeline_name)
        source_stage = response["pipeline"]["stages"][0]
        source_actions = source_stage["actions"]
        for action in source_actions:
            if action["actionTypeId"]["category"] == "Source":
                if action["actionTypeId"]["provider"] == "CodeStarSourceConnection":
                    return action["configuration"]["BranchName"]
        return None
    except Exception as e:
        print(f"Error getting pipeline source branch: {str(e)}")
        return None

##############################################################################
## Aggregate Final Output
##############################################################################
def _aggregate_response(error_info, solution):
    return {
        "status": "success",
        "pipeline_info": {
            "name": error_info.get("pipeline_name"),
            "stage": error_info.get("stage"),
        },
        "solution_recommendations": {
            "solution": solution
        },
    }
    
##############################################################################
## Main function called in Error Handler Function
##############################################################################
@app.entrypoint
def orchestrate_analysis(payload) -> Dict[str, Any]:
    try:
        pipeline_event = payload.get("event")

        branch_name = get_pipeline_source_branch(pipeline_event)
        logger.info(f"Branch Name: {branch_name}")

        error_info = _extract_error_info(pipeline_event)
        logger.info(f"Error Info: {error_info}")

        repo_structure = handle_repo_structure({"branch_name": branch_name})

        logger.info(f"Repo Structure: {repo_structure}")

        analyzed_logs = handle_log_analysis({"error_info": error_info, "pipeline_event": pipeline_event})

        solution = handle_solution_provider({"error_context": analyzed_logs, "repo_structure": repo_structure})

        return _aggregate_response(error_info, solution)
    
    except Exception as e:
        return {"status": "error", "message": str(e)}

if __name__ == "__main__":
    app.run()