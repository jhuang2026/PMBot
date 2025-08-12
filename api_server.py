"""
FastAPI server for PM Chatbot with MCP integration
Provides REST API endpoints and exposes them as MCP tools for agent access
Updated: Force cache-busting rebuild for MCP endpoints
"""

import os
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# MCP integration
try:
    from fastapi_mcp import FastApiMCP
    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    logger.warning("fastapi_mcp not available. Install with: pip install fastapi-mcp")

# Import our existing modules
from pm_chatbot_main import PMChatbot
from atlassian_client import AtlassianClient
from rfe_manager import RFEGuidelinesManager

# Import authentication
from auth import verify_token, verify_token_with_permissions, get_auth_info

# Initialize FastAPI app
app = FastAPI(
    title="PM Chatbot API",
    description="REST API for RFE creation, validation, and JIRA integration with MCP support",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize MCP Server (will be configured after all endpoints are defined)
mcp_server = None

# Global instances
pm_chatbot: Optional[PMChatbot] = None
atlassian_client: Optional[AtlassianClient] = None
guidelines_manager: Optional[RFEGuidelinesManager] = None

# Pydantic Models
class RFEGenerationRequest(BaseModel):
    prompt: str = Field(..., description="Description of the enhancement request")
    context: Optional[str] = Field(None, description="Additional context")
    selected_product: Optional[str] = Field(None, description="Product to focus on for documentation context")

class RFEGenerationResponse(BaseModel):
    rfe_content: str = Field(..., description="Generated RFE content")
    retrieved_docs: Optional[List[Dict]] = Field(None, description="Documents used for context")
    timestamp: datetime = Field(default_factory=datetime.now)

class RFEValidationRequest(BaseModel):
    rfe_content: str = Field(..., description="RFE content to validate")

class RFEValidationResponse(BaseModel):
    missing_required: List[str] = Field(..., description="Missing required sections")
    suggestions: List[str] = Field(..., description="Improvement suggestions")
    strengths: List[str] = Field(..., description="Content strengths")
    score: int = Field(..., description="Validation score (0-100)")

class JIRAIssueCreateRequest(BaseModel):
    project_key: str = Field(..., description="JIRA project key")
    summary: str = Field(..., description="Issue summary")
    description: str = Field(..., description="Issue description")
    issue_type: str = Field(default="Feature Request", description="Issue type")

class JIRAIssueUpdateRequest(BaseModel):
    summary: Optional[str] = Field(None, description="Updated summary")
    description: Optional[str] = Field(None, description="Updated description")
    issue_type: Optional[str] = Field(None, description="Updated issue type")

class JIRAIssueResponse(BaseModel):
    key: str = Field(..., description="JIRA issue key")
    summary: str = Field(..., description="Issue summary")
    status: str = Field(..., description="Issue status")
    url: str = Field(..., description="JIRA issue URL")

class DocumentSearchRequest(BaseModel):
    query: str = Field(..., description="Search query")
    product: Optional[str] = Field(None, description="Product to search within")
    top_k: int = Field(default=5, description="Number of results to return")

class DocumentSearchResponse(BaseModel):
    results: List[Dict] = Field(..., description="Search results")
    total_found: int = Field(..., description="Total documents found")

class ModelSwitchRequest(BaseModel):
    model_key: str = Field(..., description="Model key to switch to")

class HealthResponse(BaseModel):
    status: str = Field(..., description="Service status")
    timestamp: datetime = Field(default_factory=datetime.now)
    components: Dict[str, bool] = Field(..., description="Component health status")

# Dependency functions

async def get_pm_chatbot():
    """Dependency to get initialized PM chatbot"""
    global pm_chatbot
    if pm_chatbot is None:
        try:
            pm_chatbot = PMChatbot()
        except Exception as e:
            logger.error(f"Failed to initialize PM chatbot: {e}")
            raise HTTPException(status_code=500, detail="Failed to initialize chatbot service")
    return pm_chatbot

async def get_guidelines_manager():
    """Dependency to get guidelines manager"""
    global guidelines_manager
    if guidelines_manager is None:
        guidelines_manager = RFEGuidelinesManager()
    return guidelines_manager

# API Endpoints

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    chatbot = await get_pm_chatbot()
    
    components = {
        "api": True,
        "chatbot": chatbot is not None,
        "rag": chatbot.rag_manager is not None if chatbot else False,
        "jira": chatbot.atlassian_client is not None if chatbot else False,
        "mcp": MCP_AVAILABLE and mcp_server is not None
    }
    
    return HealthResponse(
        status="healthy" if all(components.values()) else "degraded",
        components=components
    )

@app.get("/debug/mcp")
async def debug_mcp():
    """Debug MCP status and configuration"""
    try:
        import fastapi_mcp
        fastapi_mcp_version = getattr(fastapi_mcp, '__version__', 'unknown')
        fastapi_mcp_available = True
        import_error = None
    except ImportError as e:
        fastapi_mcp_version = None
        fastapi_mcp_available = False
        import_error = str(e)
    
    # Count MCP endpoints
    mcp_endpoint_count = 0
    mcp_endpoints = []
    for route in app.routes:
        if hasattr(route, 'path') and '/mcp/' in route.path:
            mcp_endpoint_count += 1
            mcp_endpoints.append(route.path)
    
    return {
        "mcp_available": MCP_AVAILABLE,
        "fastapi_mcp_installed": fastapi_mcp_available,
        "fastapi_mcp_version": fastapi_mcp_version,
        "mcp_server_instance": mcp_server is not None,
        "mcp_endpoint_count": mcp_endpoint_count,
        "mcp_endpoints": mcp_endpoints,
        "import_error": import_error,
        "total_routes": len(app.routes)
    }

@app.post("/api/v1/rfe/generate", response_model=RFEGenerationResponse)
async def generate_rfe(
    request: RFEGenerationRequest,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Generate an RFE based on a prompt"""
    try:
        response, retrieved_docs = chatbot.generate_response(
            request.prompt,
            context=request.context or "",
            selected_product=request.selected_product
        )
        
        return RFEGenerationResponse(
            rfe_content=response,
            retrieved_docs=retrieved_docs
        )
    except Exception as e:
        logger.error(f"Error generating RFE: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate RFE: {str(e)}")

@app.post("/api/v1/rfe/validate", response_model=RFEValidationResponse)
async def validate_rfe(
    request: RFEValidationRequest,
    guidelines_manager: RFEGuidelinesManager = Depends(get_guidelines_manager),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Validate RFE content against guidelines"""
    try:
        validation = guidelines_manager.validate_rfe(request.rfe_content)
        return RFEValidationResponse(**validation)
    except Exception as e:
        logger.error(f"Error validating RFE: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to validate RFE: {str(e)}")

@app.post("/api/v1/rfe/improve")
async def improve_rfe(
    request: RFEValidationRequest,
    guidelines_manager: RFEGuidelinesManager = Depends(get_guidelines_manager),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Get improvement suggestions for RFE content"""
    try:
        suggestions = guidelines_manager.get_rfe_improvement_suggestions(request.rfe_content)
        return {"suggestions": suggestions}
    except Exception as e:
        logger.error(f"Error getting RFE improvements: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get improvements: {str(e)}")

@app.post("/api/v1/jira/issues", response_model=JIRAIssueResponse)
async def create_jira_issue(
    request: JIRAIssueCreateRequest,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Create a new JIRA issue"""
    if not chatbot.atlassian_client:
        raise HTTPException(status_code=503, detail="JIRA client not configured")
    
    try:
        result = chatbot.atlassian_client.create_jira_issue(
            request.project_key,
            request.summary,
            request.description,
            request.issue_type
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        issue_data = result["result"]
        jira_url = f"https://issues.redhat.com/browse/{issue_data['key']}"
        
        return JIRAIssueResponse(
            key=issue_data["key"],
            summary=request.summary,
            status="Open",  # New issues are typically open
            url=jira_url
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating JIRA issue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create JIRA issue: {str(e)}")

@app.get("/api/v1/jira/issues/{issue_key}")
async def get_jira_issue(
    issue_key: str,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Get JIRA issue details"""
    if not chatbot.atlassian_client:
        raise HTTPException(status_code=503, detail="JIRA client not configured")
    
    try:
        result = chatbot.atlassian_client.get_jira_issue(issue_key)
        
        if "error" in result:
            raise HTTPException(status_code=404, detail=result["error"])
        
        return {"issue": result["result"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting JIRA issue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get JIRA issue: {str(e)}")

@app.put("/api/v1/jira/issues/{issue_key}")
async def update_jira_issue(
    issue_key: str,
    request: JIRAIssueUpdateRequest,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Update an existing JIRA issue"""
    if not chatbot.atlassian_client:
        raise HTTPException(status_code=503, detail="JIRA client not configured")
    
    try:
        result = chatbot.atlassian_client.update_jira_issue(
            issue_key,
            summary=request.summary,
            description=request.description,
            issue_type=request.issue_type
        )
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return {"updated": result["result"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating JIRA issue: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update JIRA issue: {str(e)}")

@app.get("/api/v1/jira/search")
async def search_jira_issues(
    query: str,
    max_results: int = 20,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Search for similar RFEs in JIRA"""
    if not chatbot.atlassian_client:
        raise HTTPException(status_code=503, detail="JIRA client not configured")
    
    try:
        result = chatbot.atlassian_client.search_similar_rfes(query)
        
        if "error" in result:
            raise HTTPException(status_code=400, detail=result["error"])
        
        return {"search_results": result["result"]}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching JIRA issues: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search JIRA issues: {str(e)}")

@app.post("/api/v1/documents/search", response_model=DocumentSearchResponse)
async def search_documents(
    request: DocumentSearchRequest,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Search product documentation"""
    if not chatbot.rag_manager:
        raise HTTPException(status_code=503, detail="Document search not available")
    
    try:
        results = chatbot.rag_manager.search_documents(
            request.query,
            request.product,
            top_k=request.top_k
        )
        
        return DocumentSearchResponse(
            results=results or [],
            total_found=len(results) if results else 0
        )
    except Exception as e:
        logger.error(f"Error searching documents: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to search documents: {str(e)}")

@app.get("/api/v1/documents/products")
async def get_available_products(
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Get list of available products for documentation search"""
    if not chatbot.rag_manager:
        raise HTTPException(status_code=503, detail="Document search not available")
    
    try:
        return {"products": list(chatbot.rag_manager.products.keys())}
    except Exception as e:
        logger.error(f"Error getting products: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get products: {str(e)}")

@app.get("/api/v1/models")
async def get_available_models(
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Get list of available AI models"""
    try:
        models = chatbot.model_client.list_models()
        current_model = chatbot.model_client.current_model_key
        
        return {
            "models": models,
            "current_model": current_model
        }
    except Exception as e:
        logger.error(f"Error getting models: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get models: {str(e)}")

@app.post("/api/v1/models/switch")
async def switch_model(
    request: ModelSwitchRequest,
    chatbot: PMChatbot = Depends(get_pm_chatbot),
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Switch to a different AI model"""
    try:
        success = chatbot.model_client.switch_model(request.model_key)
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to switch model")
        
        return {"success": True, "current_model": request.model_key}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error switching model: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to switch model: {str(e)}")

@app.get("/api/v1/auth/info")
async def get_auth_info_endpoint(
    user_context: Dict[str, Any] = Depends(verify_token)
):
    """Get authentication information for the current user"""
    auth_info = get_auth_info()
    return {
        "user": {
            "username": user_context.get("username", "unknown"),
            "permissions": user_context.get("permissions", []),
            "token": user_context.get("token", "hidden")
        },
        "system": {
            "auth_method": auth_info["auth_method"],
            "environment": auth_info["environment"]
        }
    }

# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    logger.info("Starting PM Chatbot API server...")
    try:
        # Initialize the chatbot to verify everything works
        await get_pm_chatbot()
        
        # Log authentication configuration
        auth_info = get_auth_info()
        logger.info(f"Authentication method: {auth_info['auth_method']}")
        logger.info(f"Environment: {auth_info['environment']}")
        logger.info(f"Valid API keys configured: {auth_info['valid_keys_count']}")
        
        # Log MCP status
        if MCP_AVAILABLE:
            logger.info("MCP server available - agents can access API as tools")
        else:
            logger.warning("MCP server not available - install fastapi-mcp for agent integration")
        
        logger.info("PM Chatbot API server started successfully")
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        raise

if __name__ == "__main__":
    # Run the server
    uvicorn.run(
        "api_server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )# Deployment trigger: Fri Aug  1 21:53:24 EDT 2025

# MCP-specific endpoints that handle authentication internally
# These endpoints are created regardless of fastapi-mcp availability
# MCP helper function to get auth token from environment
def get_mcp_auth_token() -> str:
    """Get authentication token from MCP environment"""
    import os
    auth_header = os.getenv("AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header.replace("Bearer ", "")
    return "pmbot-production-token"  # Default token

# MCP-specific endpoints (no FastAPI auth required, handled internally)
@app.post("/mcp/rfe/generate", tags=["MCP Tools"])
async def mcp_generate_rfe(request: RFEGenerationRequest):
    """Generate RFE (MCP Tool) - Creates an RFE based on description"""
    token = get_mcp_auth_token()
    # Create mock auth credentials for internal use
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        chatbot = await get_pm_chatbot()
        
        # Call the actual generation logic
        response, retrieved_docs = chatbot.generate_response(
            request.prompt,
            context=request.context or "",
            selected_product=request.selected_product
        )
        
        return RFEGenerationResponse(
            rfe_content=response,
            retrieved_docs=retrieved_docs
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

@app.post("/mcp/rfe/validate", tags=["MCP Tools"])
async def mcp_validate_rfe(request: RFEValidationRequest):
    """Validate RFE (MCP Tool) - Validates RFE content against guidelines"""
    token = get_mcp_auth_token()
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        guidelines_manager = await get_guidelines_manager()
        
        # Call the actual validation logic
        validation_result = guidelines_manager.validate_rfe(request.rfe_content)
        
        return RFEValidationResponse(
            missing_required=validation_result['missing_required'],
            suggestions=validation_result['suggestions'],
            strengths=validation_result['strengths'],
            score=validation_result['score']
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

@app.post("/mcp/documents/search", tags=["MCP Tools"])
async def mcp_search_documents(request: DocumentSearchRequest):
    """Search Documents (MCP Tool) - Search Red Hat product documentation"""
    token = get_mcp_auth_token()
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        chatbot = await get_pm_chatbot()
        
        # Call the actual search logic
        results = chatbot.rag_manager.search_documents(
            query=request.query,
            product=request.product,
            top_k=request.top_k or 5
        )
        
        return DocumentSearchResponse(
            results=results,
            total_found=len(results)
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

@app.get("/mcp/models", tags=["MCP Tools"])
async def mcp_get_models():
    """Get Available Models (MCP Tool) - List all available AI models"""
    token = get_mcp_auth_token()
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        chatbot = await get_pm_chatbot()
        
        # Return available models
        return {"models": chatbot.model_client.list_models()}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

@app.post("/mcp/jira/issues", tags=["MCP Tools"])
async def mcp_create_jira_issue(request: JIRAIssueCreateRequest):
    """Create JIRA Issue (MCP Tool) - Create a new JIRA issue from RFE content"""
    token = get_mcp_auth_token()
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        chatbot = await get_pm_chatbot()
        
        # Create JIRA issue
        if not chatbot.atlassian_client:
            raise HTTPException(status_code=500, detail="JIRA client not available")
            
        issue = chatbot.atlassian_client.create_jira_issue(
            project_key=request.project_key,
            summary=request.summary,
            description=request.description,
            issue_type=request.issue_type
        )
        
        return JIRAIssueResponse(
            key=issue['result']['key'],
            summary=issue['result']['fields']['summary'],
            status=issue['result']['fields']['status']['name'],
            url=f"https://issues.redhat.com/browse/{issue['result']['key']}"
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

@app.put("/mcp/jira/issues/{issue_key}", tags=["MCP Tools"])
async def mcp_update_jira_issue(issue_key: str, request: JIRAIssueUpdateRequest):
    """Update JIRA Issue (MCP Tool) - Update an existing JIRA issue"""
    token = get_mcp_auth_token()
    from fastapi.security import HTTPAuthorizationCredentials
    from auth import verify_token
    
    try:
        mock_credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        user_context = await verify_token(mock_credentials)
        
        # Get properly initialized dependencies
        chatbot = await get_pm_chatbot()
        
        # Update JIRA issue
        if not chatbot.atlassian_client:
            raise HTTPException(status_code=500, detail="JIRA client not available")
            
        issue = chatbot.atlassian_client.update_jira_issue(
            issue_key=issue_key,
            summary=request.summary,
            description=request.description,
            issue_type=request.issue_type
        )
        
        return JIRAIssueResponse(
            key=issue['result']['key'],
            summary=issue['result']['summary'],
            status=issue['result']['status'],
            url=f"https://issues.redhat.com/browse/{issue['result']['key']}"
        )
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Authentication failed: {e}")

# Now configure the MCP server to expose these endpoints as tools
if MCP_AVAILABLE:
    try:
        from fastapi_mcp import FastApiMCP
        # Create MCP server - now it can expose the /mcp/* endpoints as tools
        mcp_server = FastApiMCP(app)
        mcp_server.mount()  # Mounts MCP server at /mcp endpoint
        
        logger.info("MCP server mounted at /mcp - Agents can now access API as MCP tools")
        logger.info("MCP tools available: rfe/generate, rfe/validate, documents/search, models, jira/issues")
        logger.info("MCP authentication: Token from AUTHORIZATION environment variable")
    except Exception as e:
        logger.error(f"Failed to initialize MCP server: {e}")
        MCP_AVAILABLE = False
else:
    logger.warning("MCP functionality disabled - agents will not be able to access this API")

# Deployment trigger for auth fix: Fri Aug  1 22:03:33 EDT 2025
