import logging
import requests
from typing import Dict, List, Optional, Any
from atlassian import Jira
import ssl
import urllib3

# Configure logging
logger = logging.getLogger(__name__)

class AtlassianClient:
    """Client for interacting with JIRA"""
    
    def __init__(self):
        self.jira_client = None
        self.config = {}
        self.ssl_verify = True
        
    def configure(self, config: Dict) -> bool:
        """Configure JIRA client"""
        try:
            self.config = config
            self.ssl_verify = config.get('ssl_verify', True)
            
            # Disable SSL warnings if verification is disabled
            if not self.ssl_verify:
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Initialize JIRA client
            if config.get('jira_url') and config.get('jira_token'):
                self.jira_client = Jira(
                    url=config['jira_url'],
                    token=config['jira_token'],
                    verify_ssl=self.ssl_verify
                )
                logger.info("JIRA client configured")
                return True
            else:
                logger.error("JIRA URL and token are required")
                return False
            
        except Exception as e:
            logger.error(f"Failed to configure JIRA client: {e}")
            return False
    
    def test_connection(self) -> Dict[str, Any]:
        """Test connection to JIRA"""
        result = {
            "jira": False,
            "errors": []
        }
        
        # Test JIRA connection
        if self.jira_client:
            try:
                # Try to get projects list (should work with minimal permissions)
                projects = self.jira_client.projects()
                if projects is not None:  # Could be empty list []
                    result["jira"] = True
                    logger.info("JIRA connection successful")
            except Exception as e:
                error_msg = f"JIRA connection failed: {str(e)}"
                result["errors"].append(error_msg)
                logger.error(error_msg)
        else:
            result["errors"].append("JIRA client not configured")
        
        return result
    
    def create_jira_issue(self, project_key: str, summary: str, description: str, 
                         issue_type: str = "Story") -> Dict[str, Any]:
        """Create a JIRA issue"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            # First, try to get project info to validate it exists
            try:
                project_info = self.jira_client.project(project_key)
                if not project_info:
                    return {"error": f"Project '{project_key}' not found or not accessible"}
            except Exception as e:
                return {"error": f"Cannot access project '{project_key}': {str(e)}"}
            
            issue_data = {
                "project": {"key": project_key},
                "summary": summary,
                "description": description,
                "issuetype": {"name": issue_type}
            }
            
            # Create the issue
            result = self.jira_client.issue_create(fields=issue_data)
            
            if result:
                logger.info(f"Created JIRA issue: {result.get('key', 'Unknown key')}")
                return {"result": result}
            else:
                return {"error": "Failed to create issue - no result returned"}
                
        except Exception as e:
            error_msg = f"Failed to create JIRA issue: {str(e)}"
            logger.error(error_msg)
            
            # Provide more specific error messages for common issues
            if "Issue type" in str(e) and "does not exist" in str(e):
                return {"error": f"Issue type '{issue_type}' does not exist in project '{project_key}'. Try 'Story' or 'Task'."}
            elif "Field" in str(e) and "required" in str(e):
                return {"error": f"Missing required field(s) for project '{project_key}': {str(e)}"}
            else:
                return {"error": error_msg}
    
    def get_jira_issue(self, issue_key: str) -> Dict[str, Any]:
        """Get details of a JIRA issue"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            issue = self.jira_client.issue(issue_key)
            if issue:
                return {
                    "result": {
                        "key": issue["key"],
                        "summary": issue["fields"]["summary"],
                        "description": issue["fields"].get("description", ""),
                        "status": issue["fields"]["status"]["name"],
                        "assignee": issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned",
                        "reporter": issue["fields"]["reporter"]["displayName"],
                        "created": issue["fields"]["created"],
                        "updated": issue["fields"]["updated"]
                    }
                }
            else:
                return {"error": f"Issue {issue_key} not found"}
                
        except Exception as e:
            error_msg = f"Failed to get JIRA issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
    
    def update_jira_issue(self, issue_key: str, summary: str = None, description: str = None, 
                         issue_type: str = None, **other_fields) -> Dict[str, Any]:
        """Update an existing JIRA issue"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            # First, verify the issue exists
            try:
                existing_issue = self.jira_client.issue(issue_key)
                if not existing_issue:
                    return {"error": f"Issue {issue_key} not found"}
            except Exception as e:
                return {"error": f"Cannot access issue {issue_key}: {str(e)}"}
            
            # Build update fields
            update_fields = {}
            
            if summary:
                update_fields["summary"] = summary
            
            if description:
                update_fields["description"] = description
                
            if issue_type:
                update_fields["issuetype"] = {"name": issue_type}
            
            # Add any other fields
            update_fields.update(other_fields)
            
            if not update_fields:
                return {"error": "No fields provided to update"}
            
            # Update the issue
            result = self.jira_client.issue_update(issue_key, fields=update_fields)
            
            # The update method typically returns None on success
            if result is None or result == "":
                logger.info(f"Updated JIRA issue: {issue_key}")
                # Get updated issue details
                updated_issue = self.jira_client.issue(issue_key)
                return {
                    "result": {
                        "key": updated_issue["key"],
                        "summary": updated_issue["fields"]["summary"],
                        "description": updated_issue["fields"].get("description", ""),
                        "status": updated_issue["fields"]["status"]["name"],
                        "updated": updated_issue["fields"]["updated"]
                    }
                }
            else:
                return {"error": f"Update returned unexpected result: {result}"}
                
        except Exception as e:
            error_msg = f"Failed to update JIRA issue {issue_key}: {str(e)}"
            logger.error(error_msg)
            
            # Provide more specific error messages for common issues
            if "Permission" in str(e) or "permission" in str(e):
                return {"error": f"Insufficient permissions to update issue {issue_key}"}
            elif "Issue type" in str(e) and "does not exist" in str(e):
                return {"error": f"Issue type '{issue_type}' does not exist in this project"}
            else:
                return {"error": error_msg}

    def search_jira_issues(self, jql: str, max_results: int = 50) -> Dict[str, Any]:
        """Search JIRA issues using JQL"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            results = self.jira_client.jql(jql, limit=max_results)
            
            if results and "issues" in results:
                issues = []
                for issue in results["issues"]:
                    issues.append({
                        "key": issue["key"],
                        "summary": issue["fields"]["summary"],
                        "status": issue["fields"]["status"]["name"],
                        "assignee": issue["fields"]["assignee"]["displayName"] if issue["fields"]["assignee"] else "Unassigned",
                        "created": issue["fields"]["created"]
                    })
                
                return {
                    "result": {
                        "total": results.get("total", 0),
                        "issues": issues
                    }
                }
            else:
                return {"result": {"total": 0, "issues": []}}
                
        except Exception as e:
            error_msg = f"Failed to search JIRA issues: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
    
    def test_issue_creation_capability(self, project_key: str) -> Dict[str, Any]:
        """Test if we can create issues in the specified project"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            # Try to get project info
            project_info = self.jira_client.project(project_key)
            if not project_info:
                return {"error": f"Project '{project_key}' not found"}
            
            # Get issue types
            issue_types_result = self.get_project_issue_types(project_key)
            if "error" in issue_types_result:
                return issue_types_result
            
            issue_types = [it["name"] for it in issue_types_result["result"]]
            
            # Try to get current user info to verify permissions
            try:
                current_user = self.jira_client.current_user()
                user_info = current_user.get("displayName", "Unknown") if current_user else "Unknown"
            except:
                user_info = "Cannot determine user"
            
            return {
                "result": {
                    "project_accessible": True,
                    "project_name": project_info.get("name", project_key),
                    "available_issue_types": issue_types,
                    "current_user": user_info,
                    "can_create_issues": len(issue_types) > 0
                }
            }
            
        except Exception as e:
            error_msg = f"Failed to test issue creation capability: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    def get_project_issue_types(self, project_key: str) -> Dict[str, Any]:
        """Get available issue types for a project"""
        if not self.jira_client:
            return {"error": "JIRA client not configured"}
        
        try:
            # Get project metadata including issue types
            project_meta = self.jira_client.project_meta(project_key)
            
            if project_meta and "projects" in project_meta:
                projects = project_meta["projects"]
                if projects:
                    issue_types = []
                    for issue_type in projects[0].get("issuetypes", []):
                        issue_types.append({
                            "name": issue_type["name"],
                            "id": issue_type["id"],
                            "description": issue_type.get("description", "")
                        })
                    
                    return {"result": issue_types}
                else:
                    return {"error": f"No project data found for '{project_key}'"}
            else:
                return {"error": f"Could not get metadata for project '{project_key}'"}
                
        except Exception as e:
            error_msg = f"Failed to get issue types for project '{project_key}': {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}

    def search_similar_rfes(self, search_terms: str) -> Dict[str, Any]:
        """Search for similar RFEs in JIRA"""
        # Construct JQL to search for RFEs with similar terms
        jql_terms = " OR ".join([f'summary ~ "{term}"' for term in search_terms.split()])
        jql = f'project = "RHOAIRFE" AND ({jql_terms}) ORDER BY created DESC'
        
        return self.search_jira_issues(jql, max_results=20) 