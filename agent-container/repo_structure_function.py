import json
import boto3
import os
# import urllib.request
# import urllib.error
import requests
from urllib.parse import urlparse
import logging

logger = logging.getLogger()
logger.setLevel(logging.INFO)

AWS_DEFAULT_REGION = os.environ.get('AWS_DEFAULT_REGION', 'us-east-1')

class RepoStructureFunction:
    def __init__(self):
        self.secrets_client = boto3.client("secretsmanager", region_name=AWS_DEFAULT_REGION)

    ##############################################################################
    ## Analyze Repo Structure
    ##############################################################################
    def analyze_repository_structure(self, branch_name: str) -> dict:
        try:
            credentials = self._get_github_credentials()
            if not credentials:
                return {"error": "Failed to retrieve GitHub credentials"}
            repo_url = credentials.get("repo_url")
            access_token = credentials.get("access_token")
            owner, repo = self._parse_github_url(repo_url)
            if not owner or not repo:
                return {"error": "Invalid GitHub URL format"}
            tree_data = self._get_repo_tree(owner, repo, branch_name, access_token)
            if not tree_data:
                return {"error": "Failed to fetch repository tree"}
            file_structure = self._build_file_structure(tree_data)
            file_paths = self._extract_file_paths(tree_data)
            dependencies = self._analyze_dependencies(
                tree_data, owner, repo, access_token
            )

            return {
                "status": "success",
                "repo_url": repo_url,
                "branch_name": branch_name,
                "file_structure": file_structure,
                "file_paths": file_paths,
                "dependencies": dependencies,
                "total_files": len(file_paths),
                "analysis": {
                    "config_files": [f for f in file_paths if self._is_config_file(f)],
                    "source_files": [f for f in file_paths if self._is_source_file(f)],
                    "build_files": [f for f in file_paths if self._is_build_file(f)],
                    "deployment_files": [
                        f for f in file_paths if self._is_deployment_file(f)
                    ],
                },
            }
        except Exception as e:
            return {"error": str(e)}

    ##############################################################################
    ## Get Github Credentials if Private repo
    ##############################################################################
    def _get_github_credentials(self):
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
    def _parse_github_url(self, repo_url):
        parsed = urlparse(repo_url)
        path_parts = parsed.path.strip("/").split("/")
        print(path_parts)
        if len(path_parts) >= 2:
            return path_parts[0], path_parts[1].replace(".git", "")
        return None, None

    ##############################################################################
    ## Get Repo Structure
    ##############################################################################
    def _get_repo_tree(self, owner, repo, branch, access_token):
        url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
        logger.info(f"Fetching repository tree from: {url}")
        try:
            # req = urllib.request.Request(url)
            # req.add_header("Authorization", f"Bearer {access_token}")
            # req.add_header("Accept", "application/vnd.github.v3+json")

            # with urllib.request.urlopen(req) as response:
            #     logger.info(f"GitHub API response status: {response.status}")
                # data = json.loads(response.read().decode())
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            logger.info(
                f"Retrieved {len(data.get('tree', []))} items from repository"
            )
            return data
        except requests.exceptions.HTTPError as e:
            logger.error(f"GitHub API HTTP error: {e.response.status_code} - {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Request error: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Error fetching repository tree: {str(e)}")
            return None

    ##############################################################################
    ## Build File Structure from repo structure
    ##############################################################################
    def _build_file_structure(self, tree_data):
        structure = {}
        for item in tree_data.get("tree", []):
            path_parts = item["path"].split("/")
            current_level = structure
            for i, part in enumerate(path_parts):
                if i == len(path_parts) - 1:
                    current_level[part] = "file" if item["type"] == "blob" else {}
                else:
                    if part not in current_level:
                        current_level[part] = {}
                    current_level = current_level[part]
        return structure

    ##############################################################################
    ## Extract File Paths
    ##############################################################################
    def _extract_file_paths(self, tree_data):
        return [
            item["path"] for item in tree_data.get("tree", []) if item["type"] == "blob"
        ]

    ##############################################################################
    ## Analyze dependencies
    ##############################################################################
    def _analyze_dependencies(self, tree_data, owner, repo, access_token):
        dependencies = {}
        config_files = [
            "package.json",
            "requirements.txt",
            "pom.xml",
            "build.gradle",
            "Dockerfile",
        ]
        for item in tree_data.get("tree", []):
            if any(item["path"].endswith(cf) for cf in config_files):
                content = self._get_file_content(
                    owner, repo, item["path"], access_token
                )
                dependencies[item["path"]] = content
        return dependencies
    ##############################################################################
    ## Get File content
    ##############################################################################
    def _get_file_content(self, owner, repo, file_path, access_token):
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{file_path}"
        try:
            # req = urllib.request.Request(url)
            # req.add_header("Authorization", f"Bearer {access_token}")
            # req.add_header("Accept", "application/vnd.github.v3+json")
            # with urllib.request.urlopen(req) as response:
            #     data = json.loads(response.read().decode())
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json"
            }
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()
            if data.get("encoding") == "base64":
                import base64
                return base64.b64decode(data["content"]).decode("utf-8")
            return data.get("content", "")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching file content: {str(e)}")
            return "[Unreadable]"
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return "[Unreadable]"
    ##############################################################################
    ## Recognize file type
    ##############################################################################
    def _is_config_file(self, path):
        config_extensions = [
            ".json",
            ".yaml",
            ".yml",
            ".xml",
            ".properties",
            ".ini",
            ".conf",
        ]
        config_names = ["dockerfile", "makefile", "jenkinsfile", "buildspec"]
        return any(path.lower().endswith(ext) for ext in config_extensions) or any(
            name in path.lower() for name in config_names
        )
    def _is_source_file(self, path):
        source_extensions = [
            ".py",
            ".js",
            ".java",
            ".cpp",
            ".c",
            ".go",
            ".rs",
            ".rb",
            ".php",
            ".cs",
            ".ts",
        ]
        return any(path.lower().endswith(ext) for ext in source_extensions)
    def _is_build_file(self, path):
        build_files = [
            "build.gradle",
            "pom.xml",
            "package.json",
            "requirements.txt",
            "setup.py",
            "cargo.toml",
        ]
        return any(bf in path.lower() for bf in build_files)
    def _is_deployment_file(self, path):
        deployment_patterns = [
            "deploy",
            "k8s",
            "kubernetes",
            "helm",
            "terraform",
            "cloudformation",
            "docker",
        ]
        return any(pattern in path.lower() for pattern in deployment_patterns)

##############################################################################
## Entrypoint - Will be called from supervisor_function.py
##############################################################################
def handle_repo_structure(event):
    logger.info("Repository Structure Function started")
    logger.info(f"Event received: {json.dumps(event)}")
    try:
        branch_name = event.get("branch_name", {})
        logger.info(f"Branch name: {branch_name}")
        repo_structure_function = RepoStructureFunction()
        logger.info("Function initialized, starting repository analysis")
        result = repo_structure_function.analyze_repository_structure(branch_name)
        logger.info(f"Repository analysis completed: {result}")
        response = {"statusCode": 200, "body": json.dumps(result, indent=2)}
        logger.info(f"Response prepared: {response}")
        logger.info("Response prepared successfully")
        return response
    except Exception as e:
        logger.error(f"Repo structure function failed with error: {str(e)}")
        error_response = {
            "statusCode": 500,
            "body": json.dumps(
                {"error": f"Repo structure function execution failed: {str(e)}"}, indent=2
            ),
        }
        return error_response