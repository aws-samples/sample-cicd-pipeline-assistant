import json
import boto3
import logging
import os
# import urllib.request
import requests
from urllib.parse import urlparse
from typing import Dict, Optional

logger = logging.getLogger(__name__)  # Create named logger for this module
logger.setLevel(logging.INFO)

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

class SolutionProviderAgent:
    def __init__(self):
        # Initialize AWS clients needed for the solution
        self.bedrock_client = boto3.client("bedrock-runtime", region_name=AWS_DEFAULT_REGION)  # For Claude AI model
        self.secrets_client = boto3.client("secretsmanager", region_name=AWS_DEFAULT_REGION)   # For GitHub credentials

    ##############################################################################
    ## Main Flow
    ##############################################################################
    def _generate_solution(self, repo_structure: Dict[str, str], error_context: Dict[str, str]):
        """
        Main orchestration method that:
        1. Identifies problematic file using Claude
        2. Fetches file content from GitHub
        3. Generates solution with complete context
        """
        try:
            # STEP 1: Ask Claude to identify which file caused the error
            logger.info("Step 1: Identifying problematic file using Claude")
            problematic_file = self._identify_problematic_file(error_context, repo_structure)
            logger.info(f"Identified problematic file: {problematic_file}")
            
            # STEP 2: If a file was identified, fetch its content from GitHub
            file_content = ""
            if problematic_file:
                logger.info(f"Step 2: Fetching content for file: {problematic_file}")
                file_content = self._fetch_file_content(problematic_file, repo_structure)  # PASS repo_structure
                logger.info(f"File content fetched, length: {len(file_content)} characters")
            else:
                logger.info("Step 2: No specific file identified, proceeding without file content")
            
            # STEP 3: Generate comprehensive solution with all available context
            logger.info("Step 3: Generating solution with complete context")
            solution = self._generate_comprehensive_solution(
                repo_structure, error_context, problematic_file, file_content
            )
            
            return solution
            
        except Exception as e:
            logger.error(f"Error in solution generation: {e}")
            # Return structured error response matching expected format
            return {
                "error": "Failed to generate solution",
                "details": str(e),
                "problematic_file": None,
                "solution": "Unable to generate solution due to error"
            }
        
    ##############################################################################
    ## Identifying Files
    ##############################################################################
    def _identify_problematic_file(self, error_context: Dict, repo_structure: Dict) -> Optional[str]:
        """
        Use Claude to intelligently identify which file caused the pipeline failure
        This replaces complex regex patterns with AI intelligence
        """
        try:
            # Parse nested JSON structures from both inputs
            # error_context and repo_structure often have JSON strings in 'body' field
            if isinstance(error_context.get('body'), str):
                error_data = json.loads(error_context['body'])
            else:
                error_data = error_context
                
            if isinstance(repo_structure.get('body'), str):
                repo_data = json.loads(repo_structure['body'])
            else:
                repo_data = repo_structure
            
            # Extract list of available files from repository structure
            available_files = repo_data.get('file_paths', [])
            
            # Create focused prompt for Claude to identify the problematic file
            prompt = f"""
            Analyze this CI/CD pipeline error and identify the EXACT filename causing the issue.
            
            Pipeline Error Context: {error_data}
            Available Files in Repository: {available_files}
            
            Instructions:
            - Look for file references in error messages, logs, or stack traces
            - Return ONLY the exact filename from the available files list
            - If no specific file is mentioned, return "NONE"
            - Do not provide explanations or additional text
            
            Response format: Just the filename (e.g., "template.yaml") or "NONE"
            """
            
            # Invoke Claude with minimal token limit for efficiency
            response = self._invoke_bedrock_simple(prompt, max_tokens=50)
            filename = response.strip().strip('"')  # Clean response
            
            # Validate that the identified file actually exists in the repository
            if filename == "NONE" or filename not in available_files:
                logger.info("No valid problematic file identified")
                return None
                
            logger.info(f"Claude identified problematic file: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error identifying problematic file: {e}")
            return None
        
    ##############################################################################
    ## Fetch File Content
    ##############################################################################
    def _fetch_file_content(self, filename: str, repo_structure: Dict) -> str:  # ADD repo_structure parameter
        """
        Fetch the actual content of the problematic file from GitHub
        Uses the same GitHub API pattern as repo_structure_function.py
        """
        try:
            # Parse repo_structure to get branch_name
            if isinstance(repo_structure.get('body'), str):
                repo_data = json.loads(repo_structure['body'])
            else:
                repo_data = repo_structure
                
            branch_name = repo_data.get('branch_name', 'main')  # Extract branch_name
            logger.info(f"Using branch: {branch_name}")
            
            # Get GitHub credentials from AWS Secrets Manager
            credentials = self._get_github_credentials()
            if not credentials:
                logger.error("Failed to retrieve GitHub credentials")
                return "[Unable to fetch file content - credentials error]"
            
            # Extract repository information from credentials
            repo_url = credentials.get("repo_url")
            access_token = credentials.get("access_token")
            
            # Parse GitHub URL to get owner and repository name
            owner, repo = self._parse_github_url(repo_url)
            if not owner or not repo:
                logger.error("Invalid GitHub URL format")
                return "[Unable to fetch file content - invalid repo URL]"
            
            # Fetch file content using GitHub Contents API with branch
            content = self._get_file_content_from_github(owner, repo, filename, access_token, branch_name)  # PASS branch_name
            
            if content == "[Unreadable]":
                logger.warning(f"File {filename} content is unreadable")
                return f"[File {filename} exists but content is unreadable]"
            
            logger.info(f"Successfully fetched content for {filename}")
            return content
            
        except Exception as e:
            logger.error(f"Error fetching file content for {filename}: {e}")
            return f"[Error fetching content for {filename}: {str(e)}]"
        
    ##############################################################################
    ## Solution invoking
    ##############################################################################
    def _generate_comprehensive_solution(self, repo_structure: Dict, error_context: Dict, problematic_file: Optional[str], file_content: str) -> str:
        """
        Generate the final solution using Claude with complete context:
        - Original error context and logs
        - Repository structure
        - Specific problematic file identified
        - Actual content of the problematic file
        """
        # Build comprehensive prompt with all available information
        prompt = f"""
        You are a CI/CD pipeline expert. Analyze this pipeline failure and provide a detailed solution.
        
        ERROR CONTEXT AND LOGS:
        {error_context}
        
        REPOSITORY STRUCTURE:
        {repo_structure}
        
        PROBLEMATIC FILE IDENTIFIED: {problematic_file or "No specific file identified"}
        
        FILE CONTENT:
        {file_content if file_content else "No file content available"}
        
        TASK:
        Provide a comprehensive solution plan with:
        1. Root cause analysis of the pipeline failure
        2. Specific fixes required
        3. Exact changes needed in files (if applicable)
        4. Provide the complete code after applying the fixes with inline for better understanding
        5. Step-by-step resolution instructions
        6. Prevention recommendations
        
        Format your response as a structured solution plan.
        """
        
        try:
            # Generate solution using Claude with higher token limit for detailed response
            solution = self._invoke_bedrock(prompt)
            logger.info("Comprehensive solution generated successfully")
            return solution
            
        except Exception as e:
            logger.error(f"Error generating comprehensive solution: {e}")
            return f"Error generating solution: {str(e)}"
        
    ##############################################################################
    ## Get Github Credentials if Private repo
    ##############################################################################
    def _get_github_credentials(self) -> Optional[Dict]:
        """
        Retrieve GitHub credentials from AWS Secrets Manager
        Same pattern as used in repo_structure_function.py
        """
        secret_id = os.environ.get("SECRET_ID")
        logger.info(f"Looking for SECRET_ID: {secret_id}")
        if not secret_id:
            logger.error("SECRET_ID environment variable not set")
            return None
        try:
            logger.info(f"Fetching secret: {secret_id}")
            response = self.secrets_client.get_secret_value(SecretId=secret_id)
            credentials = json.loads(response["SecretString"])
            logger.info("GitHub credentials retrieved successfully")
            return credentials
        except Exception as e:
            logger.error(f"Failed to get GitHub credentials: {str(e)}")
            return None
        
    ##############################################################################
    ## Parsing Url To Get OWNER and REPO Name
    ##############################################################################
    def _parse_github_url(self, repo_url: str) -> tuple:
        """
        Parse GitHub URL to extract owner and repository name
        Example: https://github.com/owner/repo.git -> (owner, repo)
        """
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip("/").split("/")
        logger.info(f"URL Path parts {path_parts}")
        if len(path_parts) >= 2:
            return path_parts[0], path_parts[1].replace(".git", "")
        return None, None

    ##############################################################################
    ## Get File Content
    ##############################################################################
    def _get_file_content_from_github(self, owner: str, repo: str, file_path: str, access_token: str, branch_name: str) -> str:  # ADD branch_name parameter
        """
        Fetch file content from GitHub using Contents API
        Same implementation as repo_structure_function.py
        """
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}?ref={branch_name}"  # ADD ?ref={branch_name}
        try:
            # req = urllib.request.Request(url)
            # req.add_header("Authorization", f"Bearer {access_token}")
            # req.add_header("Accept", "application/vnd.github.v3+json")
            
            # with urllib.request.urlopen(req) as response:
            #     logger.info(f"GitHub API response status: {response.status}")
            #     data = json.loads(response.read().decode())
            #     logger.info(
            #         f"Retrieved {data} items from repository"
            #     )
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(f"Retrieved {data} items from repository")
            
            # Decode base64 content if needed
            if data.get("encoding") == "base64":
                import base64
                decoded_data = base64.b64decode(data["content"]).decode("utf-8")
                logger.info(f"Decoded content for file {decoded_data}")
                return decoded_data
            return data.get("content", "")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching file content from GitHub: {e}")
            return "[Unreadable]"
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return "[Unreadable]"
        
    ##############################################################################
    ## Get File Name from Model
    ##############################################################################
    def _invoke_bedrock_simple(self, prompt: str, max_tokens: int = 50) -> str:
        """
        Simple Bedrock invocation for short responses (like filename identification)
        """
        try:
            response = self.bedrock_client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": max_tokens,
                    "messages": [{
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }]
                })
            )
            result = json.loads(response.get("body").read())
            return result.get("content", [{}])[0].get("text", "No response generated")
        except Exception as e:
            logger.error(f"Error invoking Bedrock (simple): {e}")
            return "Error"
        
    ##############################################################################
    ## Get solution from model
    ##############################################################################
    def _invoke_bedrock(self, prompt: str) -> str:
        """
        Standard Bedrock invocation for detailed responses
        """
        try:
            response = self.bedrock_client.invoke_model(
                modelId="anthropic.claude-3-sonnet-20240229-v1:0",
                body=json.dumps({
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 2048,
                    "messages": [{
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}]
                    }]
                })
            )
            result = json.loads(response.get("body").read())
            return result.get("content", [{}])[0].get("text", "No response generated")
        except Exception as e:
            logger.error(f"Error invoking Bedrock: {e}")
            return f"Error generating response: {str(e)}"
        
##############################################################################
## Entrypoint - Will be called from supervisor_function.py
##############################################################################
def handle_solution_provider(event):
    """
    Orchestrates the entire solution generation process
    """
    logger.info("Solution Provider Agent started")
    logger.info(f"Event received: {json.dumps(event)}")
    
    try:
        # Initialize the solution provider agent
        agent = SolutionProviderAgent()
        logger.info("Agent initialized successfully")
        
        # Extract input data from the event
        repo_structure = event.get("repo_structure", {})
        error_context = event.get("error_context", {})
        
        logger.info("Starting solution generation process")
        
        # Generate comprehensive solution using the enhanced workflow
        result = agent._generate_solution(repo_structure, error_context)
        logger.info(f"Solution generation completed, preparing response, {result}")
        logger.info("Solution generation completed successfully")
        
        # Return successful response
        response = {
            "statusCode": 200, 
            "body": json.dumps(result, indent=2)
        }
        logger.info("Response prepared successfully")
        return response
        
    except Exception as e:
        logger.error(f"Solution provider function failed with error: {str(e)}")
        # Return error response
        return {
            "statusCode": 500,
            "body": json.dumps({
                "error": f"Solution provider function execution failed: {str(e)}"
            }, indent=2)
        }
