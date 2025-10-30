import os
import json
import boto3
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Tuple, Optional

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

class LogAnalysisFunction:
    def __init__(self):
        self.logs_client = boto3.client("logs", region_name=AWS_DEFAULT_REGION)
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_DEFAULT_REGION)
        self.codepipeline_client = boto3.client("codepipeline", region_name=AWS_DEFAULT_REGION)
        self.ssm_client = boto3.client("ssm", region_name=AWS_DEFAULT_REGION)

    ##############################################################################
    ## Logs Analyzer
    ##############################################################################
    def analyze_logs(self, error_info: Dict[str, Any], pipeline_event: Dict[str, Any]) -> Dict[str, Any]:
        try:
            # Extract pipeline execution timeframe
            start_time, end_time = self._get_pipeline_execution_timeframe(pipeline_event)

            # Get log groups specific to the failed stage/provider
            log_groups_list = self._get_log_groups_from_ssm(
                error_info.get("pipeline_name", ""), 
                pipeline_event  # Pass pipeline_event to get stage-specific logs
            )

            # Fetch logs within execution timeframe
            log_streams = self._fetch_logs_in_timeframe(log_groups_list, start_time, end_time)

            return {
                "status": "success",
                "log_streams": log_streams,
                "execution_timeframe": {
                    "start_time": start_time.isoformat() if start_time else None,
                    "end_time": end_time.isoformat() if end_time else None,
                },
                "log_groups_list": log_groups_list,
                "failed_stage": pipeline_event.get("detail", {}).get("stage"),
                "failed_action": pipeline_event.get("detail", {}).get("action-name"),
            }
        except Exception as e:
            return {"error": str(e)}

    
    ##############################################################################
    ## Get Pipeline Time Frame
    ##############################################################################
    def _get_pipeline_execution_timeframe(self, pipeline_event: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime]]:
        """Get pipeline execution start and stop times using list-pipeline-executions"""
        try:
            detail = pipeline_event.get("detail", {})
            pipeline_name = detail.get("pipeline")
            execution_id = detail.get("execution-id")

            if not pipeline_name or not execution_id:
                logger.warning("Missing pipeline name or execution ID")
                return None, None

            executions = []
            paginator = self.codepipeline_client.get_paginator('list_pipeline_executions')
            
            # Use pagination to get all executions
            for page in paginator.paginate(pipelineName=pipeline_name):
                executions.extend([
                    e for e in page["pipelineExecutionSummaries"] 
                    if e["pipelineExecutionId"] == execution_id
                ])

            logger.info(f"Found {len(executions)} executions for pipeline {pipeline_name}")

            if executions:
                start_time = executions[0]["startTime"]
                end_time = executions[0]["lastUpdateTime"]
                
                # Ensure UTC timezone
                if start_time.tzinfo is None:
                    start_time = start_time.replace(tzinfo=timezone.utc)
                if end_time.tzinfo is None:
                    end_time = end_time.replace(tzinfo=timezone.utc)
                    
                logger.info(f"Pipeline execution timeframe (UTC): {start_time.isoformat()} to {end_time.isoformat()}")
                return start_time, end_time
            
            logger.warning(f"No executions found for pipeline {pipeline_name} with ID {execution_id}")
            return None, None
        except Exception as e:
            logger.error(f"Error getting pipeline execution timeframe: {str(e)}")
            return None, None

    ##############################################################################
    ## Get List of Log Groups from SSM parameter
    ##############################################################################
    def _get_log_groups_from_ssm(self, pipeline_name: str, pipeline_event: Dict[str, Any]) -> List[str]:
        """Get log groups specific to the failed stage/provider from SSM parameters"""
        log_groups = []
        
        # Extract stage, action, and provider from pipeline failure event
        detail = pipeline_event.get("detail", {})
        stage_name = detail.get("stage")
        action_name = detail.get("action")
        provider = detail.get("type", {}).get("provider")
        
        if not stage_name or not action_name or not provider:
            raise ValueError(f"Missing required information in pipeline event - stage: {stage_name}, action: {action_name}, provider: {provider}")
        
        logger.info(f"Found failure in provider: {provider}, stage: {stage_name}, action: {action_name}")
        
        # CodeBuild is special - it has both event and native log groups
        if provider == "CodeBuild":
            event_param = f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/codebuild-event-log-group"
            native_param = f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/codebuild-native-log-group"
            
            for param_path in [event_param, native_param]:
                try:
                    response = self.ssm_client.get_parameter(Name=param_path)
                    log_group = response["Parameter"]["Value"].strip()
                    if log_group:
                        log_groups.append(log_group)
                        logger.info(f"Found log group: {log_group}")
                except self.ssm_client.exceptions.ParameterNotFound:
                    raise ValueError(f"SSM parameter not found: {param_path}")
        
        else:
            # All other providers only have event log groups
            param_path = f"/pipeline/{pipeline_name}/{stage_name}/{action_name}/{provider.lower()}-log-group"
            
            try:
                response = self.ssm_client.get_parameter(Name=param_path)
                log_group = response["Parameter"]["Value"].strip()
                if log_group:
                    log_groups.append(log_group)
                    logger.info(f"Found log group: {log_group}")
            except self.ssm_client.exceptions.ParameterNotFound:
                raise ValueError(f"SSM parameter not found: {param_path}")
        
        if not log_groups:
            raise ValueError(f"No log groups found for {provider} stage {stage_name}")
        
        logger.info(f"Retrieved {len(log_groups)} log groups for failed {provider} stage")
        return log_groups

    ##############################################################################
    ## Fetch logs from the correct Log stream
    ##############################################################################
    def _fetch_logs_in_timeframe(self, log_groups: List[str], start_time: datetime, end_time: datetime) -> Dict[str, Any]:
        """Fetch logs with smart context preservation"""
        
        if not start_time or not end_time:
            end_time = datetime.utcnow()
            start_time = end_time - timedelta(hours=1)

        start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)
        
        all_logs = []
        logger.info(f"Fetching logs from {start_time.isoformat()} to {end_time.isoformat()}")
        logger.info(f"Fetching logs from {start_ms} to {end_ms}")
        for log_group in log_groups:
            try:
                logger.info(f"Fetching logs from {log_group}")
                is_event_log = any(keyword in log_group for keyword in ['-event-log-group'])
                
                # Get the most recent log stream (where failure likely occurred)
                streams_response = self.logs_client.describe_log_streams(
                    logGroupName=log_group,
                    orderBy='LastEventTime',
                    descending=True,
                    limit=1  # Only get the most recent stream
                )
                
                if not streams_response['logStreams']:
                    continue
                    
                stream = streams_response['logStreams'][0]
                
                if is_event_log:
                    # Event logs: Get ALL events (usually 2-5 events total)
                    events = self._get_all_events_from_stream(log_group, stream['logStreamName'], start_ms, end_ms)
                    all_logs.extend(events)
                    logger.info(f"Found {len(events)} events in {log_group}")
                else:
                    # Native logs: Get last 30 minutes of logs around failure time
                    failure_window_start = end_ms - (30 * 60 * 1000)  # 30 min before failure
                    events = self._get_events_around_failure(log_group, stream['logStreamName'], 
                                                        failure_window_start, end_ms)
                    all_logs.extend(events)
                    logger.info(f"Found {len(events)} native logs in {log_group}")
                    
            except Exception as e:
                logger.error(f"Error fetching logs from {log_group}: {str(e)}")
                continue

        # Sort by timestamp and limit total
        all_logs.sort(key=lambda x: x['timestamp'])
        logger.info(f"Returning {len(all_logs)} logs")
        # Smart truncation: Keep event logs + recent native logs
        event_logs = [log for log in all_logs if log.get('type') == 'event']
        native_logs = [log for log in all_logs if log.get('type') == 'native']
        
        # Combine: All events + last 50 native logs
        final_logs = event_logs + native_logs[-50:]
        final_logs.sort(key=lambda x: x['timestamp'])
        logger.info(f"Returning {len(final_logs)} logs")
        return {
            "logs": final_logs,
            "total_events": len(event_logs),
            "total_native": len(native_logs),
            "log_summary": f"Found {len(event_logs)} events and {len(native_logs)} native logs"
        }
    
    ##############################################################################
    ## getting all the events from stream
    ##############################################################################
    def _get_all_events_from_stream(self, log_group: str, stream_name: str, start_ms: int, end_ms: int) -> List[Dict]:
        """Get ALL events from event log streams (usually very few)"""
        events = []
        next_token = None
        
        while True:
            response = self.logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=start_ms,
                endTime=end_ms,
                nextToken=next_token
            ) if next_token else self.logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=start_ms,
                endTime=end_ms
            )

            for event in response['events']:
                events.append({
                    'log_group': log_group,
                    'timestamp': event['timestamp'],
                    'message': event['message'],
                    'type': 'event'
                })

            next_token = response.get('nextForwardToken')
            if not next_token or not response['events']:
                break
        
        return events
    
    ##############################################################################
    ## getting events in the timeframe
    ##############################################################################
    def _get_events_around_failure(self, log_group: str, stream_name: str, start_ms: int, end_ms: int) -> List[Dict]:
        """Get logs around failure time from native logs"""
        events = []
        next_token = None
        
        while True:
            response = self.logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=start_ms,
                endTime=end_ms,
                nextToken=next_token
            ) if next_token else self.logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=stream_name,
                startTime=start_ms,
                endTime=end_ms
            )

            for event in response['events']:
                events.append({
                    'log_group': log_group,
                    'timestamp': event['timestamp'],
                    'message': event['message'],
                    'type': 'native'
                })

            next_token = response.get('nextForwardToken')
            if not next_token or not response['events'] or len(events) > 100:
                break  # Stop if too many events
        
        return events

        
##############################################################################
## Entrypoint - Will be called from supervisor_function.py
##############################################################################
def handle_log_analysis(event):
    logger.info("Log Analysis Function started")
    logger.info(f"Event: {json.dumps(event, indent=2)}")
    try:
        log_function = LogAnalysisFunction()
        error_info = event.get("error_info", {})
        pipeline_event = event.get("pipeline_event", {})
        result = log_function.analyze_logs(error_info, pipeline_event)
        return {"statusCode": 200, "body": json.dumps(result, indent=2)}
    except Exception as e:
        logger.error(f"Log analysis function failed with error: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps(
                {"error": f"Log analysis function execution failed: {str(e)}"}, indent=2
            ),
        }
