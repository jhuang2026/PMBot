# PMBot - Product Manager Assistant
# Deployment test - verified phi-4 default model working - GitHub Actions test

import streamlit as st
import requests
import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
import logging
from dotenv import load_dotenv

# LangChain imports for simple MaaS integration
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.prompts.chat import SystemMessagePromptTemplate, HumanMessagePromptTemplate, AIMessagePromptTemplate
from langchain.callbacks.base import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# Import our custom modules
from atlassian_client import AtlassianClient
from rfe_manager import RFEGuidelinesManager

# Load environment variables from .env file
load_dotenv()

# Fix Streamlit file permission issues in containers
if os.getenv("STREAMLIT_CONFIG_DIR"):
    import streamlit as st_config
    # Ensure Streamlit uses writable directories in containers
    streamlit_config_dir = os.getenv("STREAMLIT_CONFIG_DIR", "/tmp/.streamlit")
    os.makedirs(streamlit_config_dir, exist_ok=True)
    os.environ["STREAMLIT_CONFIG_DIR"] = streamlit_config_dir

# Apple Silicon compatibility fixes to prevent segfaults
import platform
if platform.machine() == 'arm64':
    # PyTorch MPS compatibility
    os.environ['PYTORCH_ENABLE_MPS_FALLBACK'] = '1'
    os.environ['PYTORCH_MPS_HIGH_WATERMARK_RATIO'] = '0.0'
    
    # Threading and multiprocessing fixes
    os.environ['TOKENIZERS_PARALLELISM'] = 'false'
    os.environ['OMP_NUM_THREADS'] = '1'
    os.environ['MKL_NUM_THREADS'] = '1'
    os.environ['VECLIB_MAXIMUM_THREADS'] = '1'
    os.environ['NUMEXPR_NUM_THREADS'] = '1'
    
    # FAISS and ML library compatibility
    os.environ['FAISS_ENABLE_GPU'] = 'OFF'
    os.environ['CUDA_VISIBLE_DEVICES'] = ''
    
    # Streamlit multiprocessing fix
    import multiprocessing
    multiprocessing.set_start_method('spawn', force=True)

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()  # Console output only - avoid file permission issues in OpenShift
    ]
)
logger = logging.getLogger(__name__)

# RAG functionality imports
try:
    from vector_database import RAGManager
    RAG_AVAILABLE = True
except ImportError as e:
    RAG_AVAILABLE = False
    logger.warning(f"RAG functionality not available: {e}")

class CleanStreamingHandler(BaseCallbackHandler):
    def __init__(self):
        self.tokens = []
        self.current_response = ""

    def on_llm_new_token(self, token: str, **kwargs) -> None:
        self.tokens.append(token)
        self.current_response += token

    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        pass

    def get_clean_response(self) -> str:
        return self.current_response.strip()

    def reset(self):
        self.tokens = []
        self.current_response = ""

class ContentManager:
    def __init__(self):
        self.stored_content = {}
        self.content_counter = 0
    
    def store_content(self, content: str, content_type: str = "response") -> str:
        self.content_counter += 1
        content_id = f"{content_type}_{self.content_counter}"
        self.stored_content[content_id] = {
            'content': content,
            'type': content_type,
            'sections': self._identify_sections(content)
        }
        return content_id
    
    def _identify_sections(self, content: str) -> Dict[str, str]:
        """Simple section identification"""
        sections = {}
        paragraphs = content.split('\n\n')
        for i, paragraph in enumerate(paragraphs, 1):
            if paragraph.strip():
                sections[f"paragraph_{i}"] = paragraph.strip()
        return sections
    
    def get_content(self, content_id: str) -> Optional[Dict[str, Any]]:
        return self.stored_content.get(content_id)
    
    def list_content(self) -> Dict[str, str]:
        return {cid: data['type'] for cid, data in self.stored_content.items()}

class SimpleMaaSClient:
    """Simple MaaS client for conversational chatbot
    
    Environment Variables Required:
    - MAAS_API_KEY: API key for MaaS service
    - MAAS_BASE_URL: Base URL for MaaS service (e.g., https://your-endpoint.com/v1)
    - MAAS_MODEL_NAME: Name of the model to use
    
    These should be provided via Kubernetes secrets in deployment.
    """
    
    def __init__(self):
        # MaaS Configuration - Load all models from environment variables (Kubernetes secrets)
        self.maas_models = {}
        
        # Define model configurations that should be loaded from secrets
        model_definitions = {
            "deepseek-r1-qwen-14b": "DeepSeek R1 Qwen 14B",
            "phi-4": "Microsoft Phi-4",
            "granite-3-3-8b-instruct": "IBM Granite 3.3 8B Instruct", 
            "llama-4-scout-17b": "Llama 4 Scout 17B",
            "mistral-small-24b": "Mistral Small 24B"
        }
        
        # Load each model configuration from environment variables
        for model_key, display_name in model_definitions.items():
            # Environment variable names match the secret keys from setup script
            env_prefix = f"MAAS_{model_key.upper().replace('-', '_')}"
            
            api_key = os.getenv(f"MAAS_{model_key.upper().replace('-', '_')}_API_KEY")
            base_url = os.getenv(f"MAAS_{model_key.upper().replace('-', '_')}_BASE_URL") 
            model_name = os.getenv(f"MAAS_{model_key.upper().replace('-', '_')}_MODEL_NAME")
            
            # Only add model if all required environment variables are present
            if api_key and base_url and model_name:
                self.maas_models[model_key] = {
                    "api_key": api_key,
                    "base_url": base_url,
                    "model_name": model_name,
                    "display_name": display_name
                }
                logger.info(f"Loaded MAAS model configuration: {model_key}")
            else:
                logger.warning(f"Incomplete configuration for model {model_key} - missing environment variables")
        
        # If no models were loaded from environment, add fallback configurations for development
        if not self.maas_models:
            logger.warning("No MAAS models configured from environment variables. Using fallback configuration.")
            self.maas_models = {
                "fallback": {
                    "api_key": "your-api-key-here",
                    "base_url": "https://your-maas-endpoint.com/v1", 
                    "model_name": "your-model-name",
                    "display_name": "Fallback Model (Not Configured)"
                }
            }
        
        logger.info(f"Initialized SimpleMaaSClient with {len(self.maas_models)} models: {list(self.maas_models.keys())}")
        
        # Default model selection (prefer DEFAULT_MODEL environment variable, then phi-4)
        default_model = os.getenv("DEFAULT_MODEL", "phi-4")
        
        if default_model in self.maas_models:
            self.current_model_key = default_model
            logger.info(f"Using configured default model: {default_model}")
        elif "phi-4" in self.maas_models:
            self.current_model_key = "phi-4"
            logger.info("Using fallback default model: phi-4")
        elif self.maas_models:
            self.current_model_key = list(self.maas_models.keys())[0]
            logger.info(f"Using first available model: {self.current_model_key}")
        else:
            self.current_model_key = "fallback"
            logger.warning("No models available, using fallback")
        self.current_backend = "maas"
        self.streaming_handler = CleanStreamingHandler()
        self.conversation_history = []
        self.content_manager = ContentManager()
        
        # Initialize the LLM
        self._initialize_llm()
    
    def _initialize_llm(self):
        """Initialize the MaaS LLM with current model configuration"""
        try:
            current_config = self.maas_models[self.current_model_key]
            
            # Get container-specific configuration from environment
            disable_ssl = os.getenv("DISABLE_SSL_VERIFICATION", "true").lower() == "true"
            request_timeout = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))
            max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))
            
            # Container-optimized configuration
            llm_config = {
                "openai_api_key": current_config["api_key"],
                "openai_api_base": current_config["base_url"],
                "model_name": current_config["model_name"],
                "temperature": 0.7,
                "max_tokens": 1024,
                "streaming": True,
                "callbacks": [self.streaming_handler],
                "top_p": 0.9,
                "presence_penalty": 0.3,
                "request_timeout": request_timeout,
                "max_retries": max_retries,
                "model_kwargs": {
                    "stream_options": {"include_usage": True}
                }
            }
            
            # Container-specific SSL and network configuration
            if disable_ssl:
                import ssl
                import urllib3
                
                # Disable SSL warnings for self-signed certificates (common in enterprise environments)
                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                
                # Set additional HTTP client options for container environments
                import httpx
                llm_config["http_client"] = httpx.Client(
                    verify=False,  # Disable SSL verification for MaaS endpoints
                    timeout=float(request_timeout),
                    limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
                )
                
                logger.info("SSL verification disabled for container environment")
            else:
                logger.info("SSL verification enabled")
            
            self.llm = ChatOpenAI(**llm_config)
            self.current_model = current_config["model_name"]
            logger.info(f"Initialized MaaS client with model: {self.current_model}")
            logger.info(f"Using endpoint: {current_config['base_url']}")
            logger.info(f"Request timeout: {request_timeout}s, Max retries: {max_retries}")
            
        except Exception as e:
            logger.error(f"Failed to initialize MaaS client: {e}")
            logger.error(f"Config: {current_config}")
            raise e
    
    def switch_model(self, model_key: str) -> bool:
        """Switch to a different MaaS model"""
        if model_key in self.maas_models:
            self.current_model_key = model_key
            try:
                self._initialize_llm()
                logger.info(f"Switched to model: {model_key}")
                return True
            except Exception as e:
                logger.error(f"Failed to switch to model {model_key}: {e}")
                return False
        else:
            logger.error(f"Model {model_key} not found in available models")
            return False

    def _build_conversation_prompt(self, current_input: str, context: str = "", rag_context: str = "") -> ChatPromptTemplate:
        system_message = """
You are an expert Product Management Assistant specialized in writing high-quality RFEs (Requests for Enhancements) based on Red Hat's RHOAIRFE project standards.

When the user provides a vague or partial request, ask thoughtful follow-up questions to fill in any gaps.

Your RFEs should include all of the following sections:
- *Problem Statement:* Explain the current limitation and who it affects (include metrics if possible).
- *User Value / Goal:* What business value or user goal is achieved?
- *Scope:* What's in scope, out of scope, and future considerations?
- *Description:* What is the proposed solution? High-level architecture or flow.
- *Success Criteria:* Measurable, specific acceptance and performance criteria.

Use bullet points and markdown formatting where appropriate. Keep a professional but clear and user-centered tone.
"""
        
        if rag_context:
            system_message += f"\n\nRelevant Product Documentation:\n{rag_context}\n\nUse this documentation to provide more accurate, detailed, and product-specific responses. Reference specific capabilities, features, and constraints mentioned in the documentation."
        
        if context:
            system_message += f"\n\nAdditional Context:\n{context}"
            
        messages = [SystemMessagePromptTemplate.from_template(system_message)]
        
        # Add conversation history
        for exchange in self.conversation_history[-10:]:  # Keep last 10 exchanges
            messages.append(HumanMessagePromptTemplate.from_template(exchange['user']))
            messages.append(AIMessagePromptTemplate.from_template(exchange['assistant']))
        
        messages.append(HumanMessagePromptTemplate.from_template(current_input))
        return ChatPromptTemplate.from_messages(messages)

    def _clean_response(self, raw_response: str) -> tuple[str, list]:
        if not raw_response:
            return "I didn't generate a response. Please try again.", []

        thinking_sections = []
        cleaned = raw_response
        
        # Check for content before </think> tag (the actual format being generated)
        if '</think>' in cleaned:
            # Split on </think> and take everything before it as thinking content
            parts = cleaned.split('</think>', 1)
            if len(parts) >= 2:
                thinking_content = parts[0].strip()
                if thinking_content:
                    thinking_sections.append(thinking_content)
                # Take everything after </think> as the actual response
                cleaned = parts[1].strip()
        
        # Also check for properly wrapped thinking tags
        thinking_patterns = [
            r'<think>(.*?)</think>',
            r'<thinking>(.*?)</thinking>'
        ]
        
        for pattern in thinking_patterns:
            matches = re.findall(pattern, cleaned, re.DOTALL | re.IGNORECASE)
            thinking_sections.extend([match.strip() for match in matches if match.strip()])
            # Remove the thinking tags from the response
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Remove other patterns
        other_patterns = [
            r'Okay, so I need to.*?\n\n',
            r'Let me think.*?\n\n',
            r'Hmm.*?\n\n'
        ]
        for pattern in other_patterns:
            cleaned = re.sub(pattern, '', cleaned, flags=re.DOTALL | re.IGNORECASE)
        
        # Clean up extra whitespace
        cleaned = re.sub(r'\n\s*\n\s*\n', '\n\n', cleaned).strip()
        final_response = cleaned if cleaned else raw_response.strip()
        
        return final_response, thinking_sections

    def _add_to_history(self, user_input: str, assistant_response: str, thinking_sections: list = None):
        entry = {
            'user': user_input, 
            'assistant': assistant_response
        }
        if thinking_sections:
            entry['thinking'] = thinking_sections
        
        self.conversation_history.append(entry)
        # Keep last 20 exchanges
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    def generate_response_with_rag(self, prompt: str, context: str = "", rag_context: str = "") -> str:
        """Generate a response using the simple MaaS client with optional RAG context"""
        if not prompt.strip():
            return "Please provide a message to respond to."
        
        try:
            logger.info(f"Generating response for prompt: {prompt[:100]}...")
            logger.info(f"Using model: {self.current_model}")
            logger.info(f"Model endpoint: {self.maas_models[self.current_model_key]['base_url']}")
            
            self.streaming_handler.reset()
            conversation_prompt = self._build_conversation_prompt(prompt, context, rag_context)
            formatted_prompt = conversation_prompt.format_messages()
            
            logger.info("Invoking LLM...")
            
            # Add timeout and retry logic for container environments
            import time
            max_attempts = int(os.getenv("LLM_MAX_RETRIES", "3"))
            last_error = None
            
            for attempt in range(max_attempts):
                try:
                    start_time = time.time()
                    response = self.llm.invoke(formatted_prompt)
                    end_time = time.time()
                    
                    logger.info(f"LLM response received in {end_time - start_time:.2f}s (attempt {attempt + 1})")
                    logger.info(f"Raw streaming response length: {len(self.streaming_handler.get_clean_response())}")
                    
                    clean_response, thinking_sections = self._clean_response(self.streaming_handler.get_clean_response())
                    
                    if not clean_response or len(clean_response.strip()) < 10:
                        logger.warning(f"Empty or very short response received: '{clean_response}'")
                        logger.warning(f"Raw response: '{self.streaming_handler.get_clean_response()}'")
                        
                        if attempt < max_attempts - 1:
                            logger.info(f"Retrying due to empty response (attempt {attempt + 1}/{max_attempts})")
                            time.sleep(2 ** attempt)  # Exponential backoff
                            continue
                        else:
                            return "I received an empty response from the model. Please try again or check the logs for more details."
                    
                    # Add to conversation history with thinking sections
                    self._add_to_history(prompt, clean_response, thinking_sections)
                    
                    logger.info(f"Successfully generated response with length: {len(clean_response)}")
                    return clean_response
                    
                except Exception as attempt_error:
                    last_error = attempt_error
                    logger.error(f"Attempt {attempt + 1} failed: {attempt_error}")
                    
                    if attempt < max_attempts - 1:
                        wait_time = 2 ** attempt
                        logger.info(f"Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                    else:
                        logger.error("All retry attempts failed")
                        raise attempt_error
            
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Error generating response: {error_msg}")
            logger.error(f"Exception type: {type(e).__name__}")
            
            # Log additional debugging information for container environments
            logger.error(f"Current model endpoint: {self.maas_models[self.current_model_key]['base_url']}")
            logger.error(f"SSL verification disabled: {os.getenv('DISABLE_SSL_VERIFICATION', 'false')}")
            
            # More specific error messages for common container issues
            if "connection" in error_msg.lower() and "error" in error_msg.lower():
                # This matches the exact error from your logs
                return (f"🔌 **Network Connection Error**\n\n"
                       f"Cannot connect to the MaaS model endpoint from the container.\n\n"
                       f"**Possible causes:**\n"
                       f"• Corporate firewall blocking external connections\n" 
                       f"• Network routing issues in OpenShift cluster\n"
                       f"• MaaS endpoint unreachable from container network\n\n"
                       f"**Next steps:**\n"
                       f"• Check if the cluster can reach: `{self.maas_models[self.current_model_key]['base_url']}`\n"
                       f"• Verify firewall rules allow HTTPS traffic\n"
                       f"• Contact your cluster administrator\n\n"
                       f"**Error details:** {error_msg}")
            elif "timeout" in error_msg.lower():
                return f"⏱️ Request timed out. The model service may be slow to respond. Please try again. Error: {error_msg}"
            elif "ssl" in error_msg.lower() or "certificate" in error_msg.lower():
                return f"🔒 SSL/Certificate error connecting to model service. Please check network configuration. Error: {error_msg}"
            elif "unauthorized" in error_msg.lower() or "401" in error_msg:
                return f"🔑 Authentication error. Please check your API key configuration. Error: {error_msg}"
            elif "not found" in error_msg.lower() or "404" in error_msg:
                return f"🔍 Model or endpoint not found. Please check your MaaS configuration. Error: {error_msg}"
            else:
                return f"❌ Error: Could not generate response. {error_msg}"
    
    def clear_memory(self):
        """Clear conversation history"""
        self.conversation_history = []
    
    def list_models(self) -> List[Dict[str, str]]:
        """List available models for MaaS backend"""
        return [
            {
                "key": key,
                "display_name": config["display_name"],
                "model_name": config["model_name"]
            }
            for key, config in self.maas_models.items()
        ]
    
    def get_backend_info(self) -> Dict:
        """Get current backend information"""
        current_config = self.maas_models[self.current_model_key]
        return {
            "backend": "MaaS",
            "model": self.current_model,
            "display_name": current_config["display_name"],
            "base_url": current_config["base_url"],
            "status": "Connected"
        }
    
    def test_network_connectivity(self) -> Dict:
        """Test network connectivity to current MaaS endpoint for container troubleshooting"""
        current_config = self.maas_models[self.current_model_key]
        endpoint_url = current_config["base_url"]
        
        logger.info(f"Testing network connectivity to: {endpoint_url}")
        
        try:
            import requests
            import urllib3
            from urllib.parse import urlparse
            
            # Disable SSL warnings for testing
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # Parse the URL to get components
            parsed_url = urlparse(endpoint_url)
            test_results = {
                "endpoint": endpoint_url,
                "hostname": parsed_url.hostname,
                "port": parsed_url.port or (443 if parsed_url.scheme == 'https' else 80),
                "scheme": parsed_url.scheme
            }
            
            # Test 1: Basic HTTP connectivity
            try:
                response = requests.get(
                    endpoint_url,
                    timeout=10,
                    verify=False,  # Disable SSL verification for testing
                    headers={"User-Agent": "PMBot-Connectivity-Test"}
                )
                test_results["http_status"] = response.status_code
                test_results["http_reachable"] = True
                test_results["http_error"] = None
            except Exception as e:
                test_results["http_reachable"] = False
                test_results["http_error"] = str(e)
                test_results["http_status"] = None
            
            # Test 2: DNS resolution
            try:
                import socket
                socket.gethostbyname(parsed_url.hostname)
                test_results["dns_resolves"] = True
                test_results["dns_error"] = None
            except Exception as e:
                test_results["dns_resolves"] = False
                test_results["dns_error"] = str(e)
            
            # Test 3: Port connectivity
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5)
                result = sock.connect_ex((parsed_url.hostname, test_results["port"]))
                sock.close()
                test_results["port_reachable"] = (result == 0)
                test_results["port_error"] = None if result == 0 else f"Connection failed with code: {result}"
            except Exception as e:
                test_results["port_reachable"] = False
                test_results["port_error"] = str(e)
            
            return test_results
            
        except Exception as e:
            logger.error(f"Network connectivity test failed: {e}")
            return {
                "endpoint": endpoint_url,
                "error": str(e),
                "test_failed": True
            }

class PMChatbot:
    def __init__(self):
        self.model_client = SimpleMaaSClient()
        self.atlassian_client = None
        self.guidelines_manager = RFEGuidelinesManager()
        
        # Initialize RAG manager if available
        self.rag_manager = None
        if RAG_AVAILABLE:
            try:
                self.rag_manager = RAGManager()
                logger.info("RAG functionality initialized")
                
                # Auto-initialize database if empty
                self._auto_initialize_rag_database()
                
            except Exception as e:
                logger.warning(f"Failed to initialize RAG: {e}")
                self.rag_manager = None
        
        # Auto-initialize Atlassian if credentials are available
        self._auto_initialize_atlassian()
    
    def _auto_initialize_rag_database(self):
        """Auto-initialize RAG database if it's empty"""
        if not self.rag_manager:
            return
        
        try:
            stats = self.rag_manager.get_stats()
            
            # Check if database is empty
            if stats['vector_database']['total_chunks'] == 0:
                logger.info("RAG database is empty, auto-initializing...")
                
                # Initialize in background to avoid blocking startup
                import threading
                def init_db():
                    try:
                        result = self.rag_manager.initialize_database()
                        if result['success']:
                            logger.info(f"Auto-initialized RAG database with {result['vector_db']['total_chunks']} chunks")
                        else:
                            logger.warning(f"Failed to auto-initialize RAG database: {result.get('error', 'Unknown error')}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-initialize RAG database: {e}")
                
                # Start initialization in background thread
                thread = threading.Thread(target=init_db, daemon=True)
                thread.start()
            else:
                logger.info(f"RAG database already initialized with {stats['vector_database']['total_chunks']} chunks")
                
        except Exception as e:
            logger.warning(f"Failed to check RAG database status: {e}")
    
    def generate_response(self, prompt: str, context: str = "", selected_product: str = None) -> tuple[str, Optional[List[Dict]]]:
        """Generate response with optional RAG context and return retrieved documents"""
        # Get RAG context if available
        rag_context = ""
        retrieved_docs = None
        
        if self.rag_manager:
            try:
                # Search for relevant documents
                retrieved_docs = self.rag_manager.search_documents(prompt, selected_product, top_k=3)
                
                # Generate context string for the LLM
                rag_context = self.rag_manager.get_context_for_query(prompt, selected_product, max_chunks=3)
                
            except Exception as e:
                logger.warning(f"Failed to get RAG context: {e}")
        
        # Generate response with RAG context
        response = self.model_client.generate_response_with_rag(prompt, context, rag_context)
        return response, retrieved_docs
    
    def initialize_atlassian(self, config: Dict) -> tuple[bool, Dict]:
        """Initialize Atlassian client with configuration"""
        try:
            self.atlassian_client = AtlassianClient()
            success = self.atlassian_client.configure(config)
            
            # Test the connection
            connection_test = self.atlassian_client.test_connection()
            
            if connection_test["jira"]:
                return True, connection_test
            else:
                return False, connection_test
        except Exception as e:
            logger.error(f"Failed to initialize Atlassian client: {e}")
            return False, {"errors": [str(e)]}
    
    def _auto_initialize_atlassian(self):
        """Auto-initialize JIRA client if environment variables are available"""
        jira_url = os.getenv("JIRA_URL")
        jira_token = os.getenv("JIRA_PERSONAL_TOKEN")
        
        if jira_url and jira_token:
            try:
                config = {
                    "jira_url": jira_url,
                    "jira_token": jira_token,
                    "ssl_verify": False
                }
                
                success, connection_test = self.initialize_atlassian(config)
                
                if success:
                    st.session_state.atlassian_configured = True
                    st.session_state.atlassian_connection_status = connection_test
                    logger.info("Auto-configured JIRA client from environment variables")
            except Exception as e:
                logger.warning(f"Failed to auto-configure JIRA: {e}")

@st.dialog("📖 RFE Guidelines Summary", width="large")
def show_guidelines_modal():
    """Display RFE guidelines in a modal popup"""
    st.markdown("""
    ### Required Sections for All RFEs:
    1. **Problem Statement** - Quantified impact and clear problem articulation
    2. **User Value/Goal** - Business justification and value proposition  
    3. **Scope Definition** - In/out of scope, future considerations
    4. **Description/Overview** - Comprehensive solution overview
    5. **Success Criteria** - Measurable, specific, time-bound criteria
    
    ### Key Focus Areas:
    - **System Capabilities** - Infrastructure, hardware, platform support
    - **User Features** - New capabilities, UI improvements, workflows
    - **Integrations** - External connections, APIs, data flows
    - **Documentation** - Knowledge transfer, process improvements
    
    ### Best Practices:
    - Use specific, measurable language with metrics
    - Focus on user needs and business value
    - Include concrete examples and context
    - Balance technical and business considerations
    - Follow proper formatting (*Section Name:*)
    
    ### Quality Standards:
    - **Specific & Measurable**: Include concrete metrics (user count, performance targets, timeframes)
    - **User-Centric**: Focus on user needs and outcomes first
    - **Actionable**: Ensure requirements are implementable by development teams
    - **Balanced**: Include both business value and technical considerations
    - **Evidence-Based**: Support claims with data, user feedback, or market research
    """)
    
    if st.button("✅ Close Guidelines", use_container_width=True):
        st.rerun()

@st.dialog("Submit & Edit JIRA Issue", width="large")
def show_jira_creation_modal():
    """Display JIRA issue creation/update form with pre-filled RFE content"""
    
    import re  # Import re module at the top of the function
    
    # Get the latest assistant response
    conversation_history = st.session_state.chatbot.model_client.conversation_history
    latest_response = ""
    suggested_summary = ""
    
    if conversation_history:
        latest_response = conversation_history[-1].get('assistant', '')
        # Try to extract a summary from the first line or first few words
        if latest_response:
            first_line = latest_response.split('\n')[0].strip()
            # Remove markdown formatting and limit length
            suggested_summary = re.sub(r'[*#]', '', first_line)[:100]
            if len(first_line) > 100:
                suggested_summary += "..."
    
    # Mode selector
    mode = st.radio(
        "Select Action:",
        ["Create New Issue", "Update Existing Demo Issue"],
        index=0,
        horizontal=True,
        help="Choose whether to create a new JIRA issue or update an existing one"
    )
    
    if mode == "Create New Issue":
        st.markdown("*Pre-filled with content from your latest chatbot response*")
    elif mode == "Update Existing Demo Issue":
        st.markdown("*Update an existing test/demo issue with new content*")
    
    # Initialize variables that may be used later
    issue_key = None  # Initialize for scope
    project_key = "RHOAIRFE"  # Default project key
    
    if mode == "Update Existing Demo Issue":
        # Hardcoded issue key for demo updates
        issue_key = "RHOAIRFE-825"
        project_key = "RHOAIRFE"  # Set internally for API calls
    
    col1, col2 = st.columns(2)
    
    with col1:
        if mode == "Create New Issue":
            project_key = st.selectbox(
                "Project Key", 
                options=["RHOAIRFE", "RHAIRFE"],
                index=0,
                help="Select the JIRA project for your issue"
            )
        else:
            # For demo updates, show hardcoded issue key (disabled)
            st.text_input(
                "Issue Key (Demo)", 
                value="RHOAIRFE-825",
                help="Hardcoded demo issue for testing updates",
                disabled=True
            )
    
    with col2:
        if mode == "Create New Issue":
            issue_type = st.selectbox(
                "Issue Type", 
                ["Feature Request"],
                index=0,
                help="Select the type of JIRA issue"
            )
        else:
            # For demo updates, show grayed out issue type
            issue_type = st.selectbox(
                "Issue Type", 
                ["Feature Request"],
                index=0,
                help="Issue type is predefined for demo updates",
                disabled=True
            )
    
    # Get summary - use suggested summary from latest response
    summary = st.text_input(
        "Summary", 
        value=suggested_summary,
        help="Brief one-line description of the RFE",
        max_chars=200
    )


    # Enhanced description editor with rich text or fallback
    st.markdown("**Description/Body**")
    
    # Rich text editor option
    # Try to import the rich text editor
    try:
        from st_tiny_editor import tiny_editor
        import markdown
        
        # Convert markdown to HTML with better nested list support
        def convert_markdown_to_html(text):
            """Convert markdown to HTML with proper nested list handling (supports multiple levels)"""
            if not text:
                return ""
            
            import re  # Import once at the top
            
            # Configure markdown with extensions for better list handling
            md = markdown.Markdown(extensions=['extra', 'nl2br', 'codehilite', 'toc'])
            
            # Custom preprocessing for multi-level nested list handling
            lines = text.split('\n')
            processed_lines = []
            i = 0
            
            def process_nested_items(start_index, base_indent):
                """Recursively process nested list items at any depth (bullets and numbers)"""
                nested_items = []
                j = start_index
                
                while j < len(lines) and lines[j].strip():
                    next_line = lines[j]
                    
                    # Check for bullet points
                    is_bullet = next_line.strip().startswith('- ') or next_line.strip().startswith('* ')
                    
                    # Check for numbered lists (1., 2., 3., etc.)
                    numbered_match = re.match(r'^(\s*)(\d+)\.\s+(.+)', next_line)
                    is_numbered = numbered_match is not None
                    
                    if is_bullet or is_numbered:
                        next_indent = len(next_line) - len(next_line.lstrip())
                        
                        if next_indent > base_indent:
                            # This is a nested item at this level
                            if is_bullet:
                                nested_content = next_line.strip()[2:]  # Remove '- ' or '* '
                                list_marker = "- "
                            else:
                                # For numbered lists, extract the content after "1. "
                                nested_content = numbered_match.group(3)
                                list_number = numbered_match.group(2)
                                list_marker = f"{list_number}. "
                            
                            # Convert indentation to markdown-compliant spacing
                            # Each level needs 4 spaces in markdown
                            if next_indent == 2:
                                markdown_indent = "    "  # First nested level
                            elif next_indent == 4:
                                markdown_indent = "        "  # Second nested level  
                            elif next_indent == 6:
                                markdown_indent = "            "  # Third nested level
                            elif next_indent == 7:
                                markdown_indent = "                "  # Fourth nested level (for bullets under numbers)
                            else:
                                # Calculate based on indentation level
                                level = max(1, (next_indent + 2) // 2)
                                markdown_indent = "    " * level
                            
                            nested_items.append(markdown_indent + list_marker + nested_content)
                            
                            # Look for deeper nesting
                            deeper_items, j = process_nested_items(j + 1, next_indent)
                            nested_items.extend(deeper_items)
                        else:
                            # Not at this nesting level anymore
                            break
                    else:
                        # Not a list item
                        break
                        
                    j += 1
                
                return nested_items, j - 1
            
            while i < len(lines):
                line = lines[i]
                
                # Check for bullet points
                is_bullet = line.strip().startswith('- ') or line.strip().startswith('* ')
                
                # Check for numbered lists (1., 2., 3., etc.)
                numbered_match = re.match(r'^(\s*)(\d+)\.\s+(.+)', line)
                is_numbered = numbered_match is not None
                
                # Handle list items (bullets and numbers)
                if is_bullet or is_numbered:
                    leading_spaces = len(line) - len(line.lstrip())
                    
                    if leading_spaces == 0:
                        # Top level item
                        if is_bullet:
                            bullet_content = line.strip()[2:]  # Remove '- ' or '* '
                            processed_lines.append('- ' + bullet_content)
                        else:
                            # Numbered list at top level
                            numbered_content = numbered_match.group(3)
                            list_number = numbered_match.group(2)
                            processed_lines.append(f'{list_number}. ' + numbered_content)
                        
                        # Process all nested levels recursively
                        nested_items, last_processed = process_nested_items(i + 1, 0)
                        processed_lines.extend(nested_items)
                        i = last_processed  # Skip the processed nested items
                    
                    elif leading_spaces >= 2:
                        # This should be handled by the recursive processing above, skip if we get here
                        pass
                    
                else:
                    # Non-list line
                    processed_lines.append(line)
                
                i += 1
            
            processed_text = '\n'.join(processed_lines)
            
            return md.convert(processed_text)
        
        # Use latest response for editor content
        content_for_editor = latest_response
        
        html_content = convert_markdown_to_html(content_for_editor)
        
        # Create the rich text editor with API key and enhanced list support
        description = tiny_editor(
            apiKey="8hrbih2mcwznjezz2omtwcixf1l2yz50ed7op74o81d6ugp7",
            height=450,
            initialValue=html_content,
            key="jira_description_editor",
            toolbar='undo redo | blocks fontfamily fontsize | bold italic underline strikethrough | link table | align lineheight | numlist bullist indent outdent | emoticons charmap | removeformat',
            menubar=False,
            plugins=[
                'advlist', 'autolink', 'lists', 'link', 'charmap', 
                'searchreplace', 'visualblocks', 'code', 'fullscreen',
                'insertdatetime', 'table', 'help', 'wordcount', 'emoticons'
            ],
            content_style="""
                body { 
                    font-family: Arial, sans-serif; 
                    font-size: 14px; 
                    line-height: 1.6; 
                } 
                /* Unordered lists (bullets) */
                ul { 
                    list-style-type: disc; 
                    margin: 8px 0;
                    padding-left: 25px;
                } 
                ul ul { 
                    list-style-type: circle; 
                    margin: 4px 0;
                    padding-left: 25px;
                } 
                ul ul ul { 
                    list-style-type: square;
                    margin: 4px 0;
                    padding-left: 25px;
                }
                ul ul ul ul { 
                    list-style-type: disc;
                    margin: 4px 0;
                    padding-left: 25px;
                }
                /* Ordered lists (numbers) */
                ol { 
                    list-style-type: decimal; 
                    margin: 8px 0;
                    padding-left: 30px;
                } 
                ol ol { 
                    list-style-type: lower-alpha; 
                    margin: 4px 0;
                    padding-left: 25px;
                } 
                ol ol ol { 
                    list-style-type: lower-roman;
                    margin: 4px 0;
                    padding-left: 25px;
                }
                ol ol ol ol { 
                    list-style-type: decimal;
                    margin: 4px 0;
                    padding-left: 25px;
                }
                /* Mixed nested lists */
                ul ol, ol ul {
                    margin: 4px 0;
                    padding-left: 25px;
                }
                li {
                    margin: 3px 0;
                    padding-left: 5px;
                }
                li > strong {
                    color: #2c3e50;
                    font-weight: 600;
                }
            """,
            advlist_bullet_styles="default,circle,disc,square",
            advlist_number_styles="default,lower-alpha,lower-greek,lower-roman,upper-alpha,upper-roman",
            lists_indent_on_tab=True,
            # Additional options for better list handling
            valid_elements="*[*]",
            extended_valid_elements="*[*]"
        )
        
        # Clean HTML content for JIRA (remove dangerous tags)
        if description:
            import html
            from bs4 import BeautifulSoup
            import re
            
            def convert_html_to_jira_format(html_content):
                """Convert HTML to JIRA wiki markup format with proper nested list support"""
                if not html_content:
                    return ""
                
                # Parse HTML
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Convert to JIRA wiki markup format with nesting support
                def process_element(element, list_level=0):
                    if element.name == 'h1':
                        return f"h1. {element.get_text().strip()}\n\n"
                    elif element.name == 'h2':
                        return f"h2. {element.get_text().strip()}\n\n"
                    elif element.name == 'h3':
                        return f"h3. {element.get_text().strip()}\n\n"
                    elif element.name == 'h4':
                        return f"h4. {element.get_text().strip()}\n\n"
                    elif element.name == 'h5':
                        return f"h5. {element.get_text().strip()}\n\n"
                    elif element.name == 'h6':
                        return f"h6. {element.get_text().strip()}\n\n"
                    elif element.name in ['strong', 'b']:
                        return f"*{element.get_text().strip()}*"
                    elif element.name in ['em', 'i']:
                        return f"_{element.get_text().strip()}_"
                    elif element.name == 'code':
                        return f"{{code}}{element.get_text()}{{code}}"
                    elif element.name == 'pre':
                        return f"{{code}}\n{element.get_text()}\n{{code}}\n\n"
                    elif element.name == 'blockquote':
                        lines = element.get_text().split('\n')
                        quoted_lines = [f"bq. {line.strip()}" for line in lines if line.strip()]
                        return '\n'.join(quoted_lines) + '\n\n'
                    elif element.name == 'p':
                        # Process nested formatting within paragraphs
                        text = ""
                        for child in element.children:
                            if hasattr(child, 'name'):
                                text += process_element(child, list_level)
                            else:
                                text += str(child)
                        return text.strip() + '\n\n'
                    elif element.name == 'br':
                        return '\n'
                    elif element.name == 'ul':
                        # Handle unordered lists with proper nesting
                        return process_list(element, 'bullet', list_level)
                    elif element.name == 'ol':
                        # Handle ordered lists with proper nesting  
                        return process_list(element, 'number', list_level)
                    elif element.name in ['li', 'span', 'div']:
                        # For these, just process children without adding extra formatting
                        text = ""
                        for child in element.children:
                            if hasattr(child, 'name'):
                                if child.name in ['ul', 'ol']:
                                    # Don't process nested lists here - they'll be handled by parent
                                    continue
                                else:
                                    text += process_element(child, list_level)
                            else:
                                text += str(child)
                        return text.strip()
                    else:
                        # For unknown tags, just return the text
                        return element.get_text()
                
                def process_list(list_element, list_type, list_level):
                    """Process lists with proper JIRA formatting"""
                    items = []
                    
                    # Create appropriate prefix based on type and level
                    if list_type == 'bullet':
                        prefix = '*' * (list_level + 1)  # *, **, *** for nesting
                    else:  # number
                        prefix = '#' * (list_level + 1)  # #, ##, ### for nesting
                    
                    for li in list_element.find_all('li', recursive=False):
                        # Extract the direct text content of this li (not nested lists)
                        item_parts = []
                        nested_content = ""
                        
                        for child in li.children:
                            if hasattr(child, 'name'):
                                if child.name in ['ul', 'ol']:
                                    # Process nested lists separately
                                    nested_type = 'bullet' if child.name == 'ul' else 'number'
                                    nested_content += process_list(child, nested_type, list_level + 1)
                                else:
                                    # Process inline formatting (bold, italic, etc.) but not other lists
                                    if child.name in ['strong', 'b']:
                                        item_parts.append(f"*{child.get_text().strip()}*")
                                    elif child.name in ['em', 'i']:
                                        item_parts.append(f"_{child.get_text().strip()}_")
                                    elif child.name == 'code':
                                        item_parts.append(f"{{code}}{child.get_text()}{{code}}")
                                    else:
                                        # For other tags, just get text
                                        item_parts.append(child.get_text().strip())
                            else:
                                # Direct text content
                                text_content = str(child).strip()
                                if text_content:
                                    item_parts.append(text_content)
                        
                        # Combine the item parts
                        item_text = ' '.join(item_parts).strip()
                        
                        # Add the main list item if it has content
                        if item_text:
                            items.append(f"{prefix} {item_text}")
                        
                        # Add any nested content
                        if nested_content:
                            items.append(nested_content.rstrip())
                    
                    return '\n'.join(items) + '\n\n' if items else ""
                
                # Process the entire document
                result = ""
                for element in soup.children:
                    if hasattr(element, 'name'):
                        result += process_element(element)
                    else:
                        result += str(element)
                
                # Clean up extra whitespace
                result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)
                result = result.strip()
                
                return result
            
            # Convert HTML to JIRA-friendly format
            description = convert_html_to_jira_format(description)
        
    except ImportError:
        st.warning("⚠️ Rich text editor not available. Install 'st-tiny-editor' for enhanced editing.")
        
        # Fallback to regular text area
        description = st.text_area(
            "Description/Body",
            value=content_for_editor,
            height=450,
            key="jira_description_fallback",
            placeholder="Enter your RFE description here. You can use Markdown formatting...",
            help="Use standard keyboard shortcuts for editing. Markdown formatting will be preserved in JIRA."
        )

    # Note: HTML to JIRA format conversion is handled above for rich text editor

    # Action buttons
    col1, col2 = st.columns(2)
    
    with col1:
        if mode == "Create New Issue":
            button_text = "🚀 Create JIRA Issue"
            action_text = "Creating JIRA issue..."
        else:
            button_text = "✏️ Update JIRA Issue"
            action_text = "Updating JIRA issue..."
        
        if st.button(button_text, use_container_width=True, type="primary"):
            # Validate required fields
            required_fields_valid = project_key and summary and description
            if mode == "Update Existing Demo Issue":
                required_fields_valid = required_fields_valid and issue_key
            
            # Debug info to help troubleshoot
            if not required_fields_valid:
                missing_fields = []
                if not project_key:
                    missing_fields.append("Project Key")
                if not summary:
                    missing_fields.append("Summary")
                if not description:
                    missing_fields.append("Description")
                if mode == "Update Existing Demo Issue" and not issue_key:
                    missing_fields.append("Issue Key")
                
                st.error(f"❌ Missing fields: {', '.join(missing_fields)}")
            
            if required_fields_valid:
                with st.spinner(action_text):
                    if mode == "Create New Issue":
                        result = st.session_state.chatbot.atlassian_client.create_jira_issue(
                            project_key, summary, description, issue_type
                        )
                    else:
                        result = st.session_state.chatbot.atlassian_client.update_jira_issue(
                            issue_key, summary=summary, description=description, issue_type=issue_type
                        )
                
                if "error" in result:
                    if mode == "Create New Issue":
                        st.error(f"❌ Error creating issue: {result['error']}")
                    else:
                        st.error(f"❌ Error updating issue: {result['error']}")
                else:
                    if mode == "Create New Issue":
                        action_verb = "Created"
                        user_action = "Create JIRA issue"
                    else:
                        action_verb = "Updated"
                        user_action = "Update JIRA issue"
                    
                    if "result" in result and isinstance(result["result"], dict):
                        issue_data = result["result"]
                        issue_key_result = issue_data.get("key", issue_key if mode == "Update Existing Demo Issue" else "Unknown")
                        
                        # Construct JIRA URL
                        jira_url = f"https://issues.redhat.com/projects/RHOAIRFE/issues/{issue_key_result}"
                        
                        # Add success message with JIRA link to chat history
                        success_message = f"✅ **JIRA Issue {action_verb} Successfully!**\n\n**Issue Key:** {issue_key_result}\n**Summary:** {summary}\n**Type:** {issue_type}\n**Project:** {project_key}\n\n🔗 **[View Issue in JIRA]({jira_url})**"
                        st.session_state.chatbot.model_client.conversation_history.append({
                            'user': f"{user_action}: {summary}",
                            'assistant': success_message
                        })
                        
                        # Set success data for modal display after closing this dialog
                        st.session_state.jira_success_data = {
                            'issue_key': issue_key_result,
                            'jira_url': jira_url,
                            'action_verb': action_verb
                        }
                        
                        # Close this dialog and show success modal
                        st.rerun()
                        
                    else:
                        st.json(result.get("result", {}))
    
    with col2:
        if st.button("❌ Cancel", use_container_width=True):
            st.rerun()

@st.dialog("🎉 JIRA Issue Success", width="medium")
def show_jira_success_modal():
    """Display JIRA success modal with view/close options"""
    if 'jira_success_data' not in st.session_state:
        st.error("No success data found")
        return
    
    success_data = st.session_state.jira_success_data
    issue_key = success_data['issue_key']
    jira_url = success_data['jira_url']
    action_verb = success_data['action_verb']
    
    st.success(f"✅ **JIRA Issue {action_verb} Successfully!**")
    st.markdown(f"**Issue Key:** `{issue_key}`")
    
    st.markdown("---")
    st.markdown("**What would you like to do next?**")
    
    # Action buttons
    col1, col2 = st.columns(2)
    
    with col1:
        st.link_button(
            "🔗 Edit Issue in JIRA",
            url=jira_url,
            use_container_width=True
        )
    
    with col2:
        if st.button("✅ Close", use_container_width=True, type="primary"):
            # Clear the success data and close modal
            del st.session_state.jira_success_data
            st.rerun()

def main():
    st.set_page_config(
        page_title="PM Chatbot - RFE Assistant",
        page_icon="🚀",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    # Handle URL-based reset (most reliable for containers)
    query_params = st.query_params
    if query_params.get("reset") == "true":
        # Clear session state and remove reset parameter
        essential_keys = ['atlassian_configured', 'atlassian_connection_status']
        saved_values = {key: st.session_state.get(key) for key in essential_keys}
        
        st.session_state.clear()
        
        # Restore essential values
        for key, value in saved_values.items():
            if value is not None:
                st.session_state[key] = value
        
        # Clear the reset parameter
        st.query_params.clear()
        st.rerun()
    
    st.title("🚀 PM Chatbot - RFE Assistant")
    st.markdown("*Your AI assistant for creating Request for Enhancements following Red Hat AI guidelines*")
    
    # Handle clear chat request (container-friendly approach)
    if st.session_state.get("clear_chat_requested", False):
        # Comprehensive clearing when flag is detected
        essential_keys = ['atlassian_configured', 'atlassian_connection_status']
        saved_values = {key: st.session_state.get(key) for key in essential_keys}
        
        # Clear everything
        st.session_state.clear()
        
        # Restore essential values
        for key, value in saved_values.items():
            if value is not None:
                st.session_state[key] = value
        
        # Reset validation flag
        st.session_state.rfe_validated = False
        
        # Don't set clear_chat_requested again to avoid loop
        st.session_state.clear_chat_requested = False

    # Initialize session state
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "chatbot" not in st.session_state:
        try:
            st.session_state.chatbot = PMChatbot()
            # Verify RAG initialization
            if st.session_state.chatbot.rag_manager is None and RAG_AVAILABLE:
                logger.warning("RAG manager is None despite RAG_AVAILABLE=True, retrying...")
                # Try to reinitialize RAG manager
                try:
                    from vector_database import RAGManager
                    st.session_state.chatbot.rag_manager = RAGManager()
                    st.session_state.chatbot._auto_initialize_rag_database()
                    logger.info("RAG manager reinitialized successfully")
                except Exception as e:
                    logger.error(f"Failed to reinitialize RAG manager: {e}")
        except Exception as e:
            logger.error(f"Failed to initialize PMChatbot: {e}")
            # Create a minimal chatbot without RAG if initialization fails
            st.error(f"Failed to initialize chatbot: {e}")
            raise
    if "atlassian_configured" not in st.session_state:
        st.session_state.atlassian_configured = False
    if "atlassian_connection_status" not in st.session_state:
        st.session_state.atlassian_connection_status = None
    if "rfe_validated" not in st.session_state:
        st.session_state.rfe_validated = False
    if "selected_product" not in st.session_state:
        st.session_state.selected_product = None
    if "rag_initialized" not in st.session_state:
        st.session_state.rag_initialized = False
    
    # Auto-initialize Atlassian if tokens are available
    if not st.session_state.atlassian_configured:
        st.session_state.chatbot._auto_initialize_atlassian()
    
    # Sidebar configuration
    with st.sidebar:
        # Main Configuration dropdown
        with st.expander("⚙️ Configuration", expanded=False):
            # Model Backend Configuration
            st.subheader("🤖 Model Backend Settings")
            
            # Get current backend info
            backend_info = st.session_state.chatbot.model_client.get_backend_info()
            
            # Display current backend status
            if backend_info['status'] == 'Connected':
                st.success(f"Backend: {backend_info['backend']}; Connected")
            else:
                st.error(f"Backend: {backend_info['backend']}; Disconnected")
            
            # Show current model
            st.caption(f"Current Model: {backend_info.get('display_name', backend_info['model'])}")
            st.caption(f"Endpoint: {backend_info['base_url']}")
            
            # Model selection
            models = st.session_state.chatbot.model_client.list_models()
            if models:
                # Get current model index
                current_model_key = st.session_state.chatbot.model_client.current_model_key
                current_index = 0
                for i, model_info in enumerate(models):
                    if model_info["key"] == current_model_key:
                        current_index = i
                        break
                
                # Initialize session state for model selection if not exists
                if "selected_model_index" not in st.session_state:
                    st.session_state.selected_model_index = current_index
                
                selected_model_index = st.selectbox(
                    "Select Model", 
                    range(len(models)),
                    format_func=lambda x: models[x]["display_name"],
                    index=st.session_state.selected_model_index,
                    key="model_selector"
                )
                
                # Only switch model if selection actually changed
                if selected_model_index != st.session_state.selected_model_index:
                    selected_model_key = models[selected_model_index]["key"]
                    success = st.session_state.chatbot.model_client.switch_model(selected_model_key)
                    if success:
                        st.session_state.selected_model_index = selected_model_index
                        st.success(f"Switched to {models[selected_model_index]['display_name']}")
                        st.rerun()
                    else:
                        st.error("Failed to switch model")
            else:
                st.error("No models available. Check your backend connection.")

            # JIRA Configuration
            st.subheader("🔗 JIRA Configuration")
            
            # Show current status
            if st.session_state.atlassian_configured:
                # Show connection details
                if st.session_state.atlassian_connection_status:
                    status = st.session_state.atlassian_connection_status
                    
                    if status.get("jira", False):
                        st.success("✅ JIRA Connection Active")
                    else:
                        st.error("❌ JIRA Connection Failed")
                    
                    if status.get("errors"):
                        with st.expander("⚠️ Connection Errors"):
                            for error in status["errors"]:
                                st.error(error)
                    
                    if st.button("🔄 Test Connection"):
                        with st.spinner("Testing connection..."):
                            test_result = st.session_state.chatbot.atlassian_client.test_connection()
                            st.session_state.atlassian_connection_status = test_result
                        st.rerun()
            else:
                st.warning("🔌 Not Connected")
            
            # Configuration form
            with st.expander("⚙️ Manual Configuration", expanded=not st.session_state.atlassian_configured):
                jira_url = st.text_input("JIRA URL", value=os.getenv("JIRA_URL", "https://issues.redhat.com/"))
                jira_token = st.text_input("JIRA Token", type="password", value=os.getenv("JIRA_PERSONAL_TOKEN", ""))
                
                if st.button("Configure JIRA"):
                    if jira_token:
                        config = {
                            "jira_url": jira_url,
                            "jira_token": jira_token,
                            "ssl_verify": False
                        }
                        
                        success, connection_test = st.session_state.chatbot.initialize_atlassian(config)
                        st.session_state.atlassian_connection_status = connection_test
                        
                        if success:
                            st.session_state.atlassian_configured = True
                            st.success("✅ JIRA configured successfully!")
                        else:
                            st.error("❌ Failed to configure JIRA")
                            if connection_test.get("errors"):
                                for error in connection_test["errors"]:
                                    st.error(error)
                    else:
                        st.error("Please provide JIRA token")
            
            # RAG Configuration and Product Selection
            st.subheader("🗂️ Product Documentation")
            
            # Debug: Show RAG status
            if RAG_AVAILABLE:
                if st.session_state.chatbot.rag_manager:
                    st.success("✅ RAG functionality active")
                else:
                    st.error("❌ RAG manager not initialized")
                    if st.button("🔄 Retry RAG Initialization"):
                        try:
                            from vector_database import RAGManager
                            st.session_state.chatbot.rag_manager = RAGManager()
                            st.session_state.chatbot._auto_initialize_rag_database()
                            st.success("RAG reinitialized!")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to reinitialize: {e}")
            else:
                st.error("❌ RAG dependencies not available")
            
            # RAG Management
            with st.expander("🔧 Document Management", expanded=False):
                if st.session_state.chatbot.rag_manager:
                    # Show RAG status
                    rag_stats = st.session_state.chatbot.rag_manager.get_stats()
                    vector_stats = rag_stats['vector_database']
                    
                    st.markdown("**📊 Database Status:**")
                    if vector_stats['index_available']:
                        st.success(f"✅ {vector_stats['total_chunks']} chunks from {vector_stats['total_documents']} documents")
                    else:
                        st.warning("⚠️ Vector database not initialized")
                    
                    # Show product breakdown
                    if vector_stats.get('products'):
                        st.markdown("**📈 By Product:**")
                        for product, stats in vector_stats['products'].items():
                            product_name = st.session_state.chatbot.rag_manager.products.get(product, {}).get('name', product)
                            st.caption(f"• {product_name}: {stats['chunk_count']} chunks")
                    
                    # Initialize/Refresh documents
                    col1, col2 = st.columns(2)
                    with col1:
                        if st.button("🔄 Initialize Database", help="Process all documents and build vector database"):
                            with st.spinner("Processing documents..."):
                                result = st.session_state.chatbot.rag_manager.initialize_database()
                                if result['success']:
                                    st.session_state.rag_initialized = True
                                    st.success("✅ Database initialized!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed: {result.get('error', 'Unknown error')}")
                    
                    with col2:
                        if st.button("♻️ Refresh All", help="Reprocess all documents from scratch"):
                            with st.spinner("Refreshing documents..."):
                                result = st.session_state.chatbot.rag_manager.initialize_database(force_refresh=True)
                                if result['success']:
                                    st.session_state.rag_initialized = True
                                    st.success("✅ Documents refreshed!")
                                    st.rerun()
                                else:
                                    st.error(f"❌ Failed: {result.get('error', 'Unknown error')}")
                    
                else:
                    st.warning("⚠️ RAG functionality not available. Check dependencies.")
        
        # Guidelines info (outside the configuration dropdown)
        if st.button("📄 View Guidelines Summary"):
            show_guidelines_modal()
        
        # Clear chat button
        if st.button("🗑️ Clear Chat", help="Clear all chat messages, model interactions, and reset the conversation"):
            # Set flag to trigger clearing
            st.session_state.clear_chat_requested = True
            
            # Clear conversation history immediately
            if hasattr(st.session_state, 'chatbot') and st.session_state.chatbot:
                st.session_state.chatbot.model_client.clear_memory()
                st.session_state.chatbot.model_client.conversation_history = []
            
            # Reset message display and validation state
            st.session_state.messages = []
            st.session_state.rfe_validated = False
            
            st.rerun()
        
        # RFE Validation
        st.markdown("### ✅ RFE Validation")
        
        if st.button("Validate Latest RFE", use_container_width=True):
            # Get the latest assistant response from conversation history
            conversation_history = st.session_state.chatbot.model_client.conversation_history
            
            if conversation_history:
                latest_response = conversation_history[-1].get('assistant', '')
                
                if latest_response:
                    validation = st.session_state.chatbot.guidelines_manager.validate_rfe(latest_response)
                    
                    # Mark as validated
                    st.session_state.rfe_validated = True
                    
                    if validation["missing_required"]:
                        st.error(f"❌ Missing required sections: {', '.join(validation['missing_required'])}")
                    
                    if validation["suggestions"]:
                        for suggestion in validation["suggestions"]:
                            st.warning(f"💡 {suggestion}")
                    
                    if not validation["missing_required"] and not validation["suggestions"]:
                        st.success("🎉 RFE looks good!")
                else:
                    st.warning("⚠️ No assistant response found to validate")
            else:
                st.warning("⚠️ No chat history found. Start a conversation first!")
        
        # Submit & Edit in JIRA button
        st.markdown("### 🎫 Submit & Edit in JIRA")
        
        # Check if requirements are met for JIRA submission
        can_submit = (
            st.session_state.rfe_validated and 
            st.session_state.atlassian_configured and
            st.session_state.chatbot.model_client.conversation_history
        )
        
        # Determine button state and help text
        if not st.session_state.rfe_validated:
            help_text = "❌ Please validate your RFE first"
        elif not st.session_state.atlassian_configured:
            help_text = "❌ Please configure JIRA connection first"
        elif not st.session_state.chatbot.model_client.conversation_history:
            help_text = "❌ No RFE content found in chat"
        else:
            help_text = "✅ Create JIRA issue from your validated RFE"
        
        if st.button(
            "📝 Submit & Edit in JIRA", 
            use_container_width=True,
            disabled=not can_submit,
            help=help_text
        ):
            show_jira_creation_modal()
    
    # Show success modal if JIRA operation was successful
    if 'jira_success_data' in st.session_state:
        show_jira_success_modal()
    
    # Create a layout that separates main content from right sidebar  
    main_area, right_sidebar = st.columns([3, 1])
    
    with main_area:
        # Chat interface takes the full main area
        # Create a container for messages that takes up most of the space
        message_container = st.container()
        
        with message_container:
            # Display chat messages from conversation history
            conversation_history = st.session_state.chatbot.model_client.conversation_history
            
            if conversation_history:
                for exchange in conversation_history:
                    with st.chat_message("user"):
                        st.markdown(exchange['user'])
                    if exchange.get('assistant'):  # Only show assistant response if it exists
                        with st.chat_message("assistant"):
                            st.markdown(exchange['assistant'])
            else:
                # Show welcome message when no chat history
                with st.chat_message("assistant"):
                    st.markdown("""
                    👋 **Welcome to the PM Chatbot - RFE Assistant!**
                    
                    **Get started by:**
                    - Describing your enhancement request below
                    - Using the quick actions in the right panel
                    - Trying the example prompts for inspiration
                    
                    **I can help you:**
                    - Structure your RFE with all required sections
                    - Use product documentation for context (select a product in sidebar)
                    - Search for existing similar RFEs
                    - Validate your RFE against guidelines
                    - Create JIRA issues (when configured)
                    
                    💡 **Tip:** Select a product in the sidebar to get relevant documentation context in your RFE responses!
                    
                    Just describe what enhancement you need, and I'll guide you through creating a proper RFE! 🚀
                    """)
        
        # Display RAG retrieval information if available
        if hasattr(st.session_state, 'last_retrieved_docs') and st.session_state.last_retrieved_docs:
            with st.expander("🔍 Documents Retrieved for Last Query", expanded=False):
                st.markdown("**The following documents were used to provide context for the response:**")
                
                for i, doc in enumerate(st.session_state.last_retrieved_docs, 1):
                    metadata = doc['metadata']
                    
                    with st.container():
                        col1, col2 = st.columns([3, 1])
                        
                        with col1:
                            st.markdown(f"**📄 Document {i}:** {metadata.get('filename', 'Unknown File')}")
                            st.markdown(f"**📦 Product:** {metadata.get('product_name', 'Unknown Product')}")
                            st.markdown(f"**📝 Preview:** {doc['text'][:200]}...")
                        
                        with col2:
                            st.metric("Similarity", f"{doc['similarity_score']:.3f}")
                            st.caption(f"Section {metadata.get('section_idx', 'N/A')}")
                            st.caption(f"Chunk {metadata.get('chunk_idx', 'N/A')}")
                        
                        if i < len(st.session_state.last_retrieved_docs):
                            st.divider()
        

        
        # Chat input at the bottom of the main area
        # Use a timestamp-based key for better container compatibility
        if "chat_input_counter" not in st.session_state:
            st.session_state.chat_input_counter = 0
        
        chat_key = f"chat_input_{st.session_state.chat_input_counter}"
        if prompt := st.chat_input("Describe your enhancement request...", key=chat_key):
            # Increment counter for next input
            st.session_state.chat_input_counter += 1
            
            # Generate assistant response
            with st.spinner("Generating response..."):
                response, retrieved_docs = st.session_state.chatbot.generate_response(
                    prompt, 
                    selected_product=st.session_state.selected_product
                )
                
                # Store retrieved docs in session state for display
                st.session_state.last_retrieved_docs = retrieved_docs
            
            # Use a more reliable rerun approach
            try:
                st.rerun()
            except Exception as e:
                logger.warning(f"Rerun failed, using fallback: {e}")
                # Fallback: Just continue execution without rerun
                pass
    
    # Fixed Right Sidebar - Quick Actions
    with right_sidebar:
        st.header("🎯 Quick Actions")

        # Example prompts
        st.subheader("💡 Example Prompts")
                
        example_prompts = {
            # Feature Addition: Platform Capability
            "Model Registry Integration": "Propose an enhancement to OpenShift AI by introducing a built-in model registry that allows users to discover, browse, and pull Red Hat-validated AI/ML models. This would improve model reusability, support governance, and accelerate onboarding for data science teams working across different environments.",

            # Hardware Enablement
            "New GPU Support": "Request support for NVIDIA L40S GPUs in OpenShift AI to enable high-throughput, low-latency inference for demanding AI workloads, including generative models and computer vision. This feature would help customers in regulated industries who require certified hardware acceleration within supported Red Hat environments.",

            # UI/UX Improvement
            "Improve Metrics Dashboard": "Enhance the metrics dashboard in OpenShift AI to include advanced filtering options (e.g., by namespace, user, or resource type), real-time updates, and the ability to export metrics to CSV or JSON. These improvements would support observability use cases and help platform administrators debug workload issues more efficiently.",

            # Documentation Enhancement
            "Better Operator Docs": "Improve the official documentation for deploying the OpenShift AI Operator in disconnected or air-gapped environments. The updated guide should include detailed steps for mirroring images, handling registry authentication, verifying deployment success, and troubleshooting common issues. This would better support enterprise users operating in secure, offline networks."
        }

        
        for prompt_type, prompt_text in example_prompts.items():
            if st.button(f"📝 {prompt_type}", key=f"example_{prompt_type}", use_container_width=True):
                # Add the example prompt to chat history as a user message (without generating response)
                st.session_state.chatbot.model_client.conversation_history.append({
                    'user': prompt_text,
                    'assistant': ''  # Empty assistant response for now
                })
                st.rerun()

        # JIRA Integration
        st.markdown("### JIRA Integration")
        if st.session_state.atlassian_configured:
            
            # JIRA Issue Lookup
            with st.expander("🔍 JIRA Issue Lookup", expanded=False):
                issue_key = st.text_input("Issue Key (e.g., RHOAIRFE-123)", key="issue_lookup")
                
                if st.button("📋 Get Issue Details") and issue_key:
                    with st.spinner(f"Getting details for {issue_key}..."):
                        # Get actual JIRA issue details
                        issue_result = st.session_state.chatbot.atlassian_client.get_jira_issue(issue_key)
                        
                        if "error" in issue_result:
                            st.error(f"Error: {issue_result['error']}")
                        else:
                            issue_data = issue_result["result"]
                            
                            # Clean and format the description
                            def clean_jira_description(description):
                                """Clean up JIRA markup and format for better display"""
                                if not description:
                                    return "*No description provided*"
                                
                                import re
                                
                                # Start with the original description
                                cleaned = description
                                
                                # 1. First handle code blocks to protect them from other conversions
                                cleaned = re.sub(r'\{code:([^}]+)\}(.*?)\{code\}', r'```\1\n\2\n```', cleaned, flags=re.DOTALL)
                                cleaned = re.sub(r'\{code\}(.*?)\{code\}', r'```\n\1\n```', cleaned, flags=re.DOTALL)
                                cleaned = re.sub(r'\{\{([^}]+)\}\}', r'`\1`', cleaned)
                                
                                # 2. Convert JIRA headers (h1., h2., etc.) to markdown
                                cleaned = re.sub(r'^h([1-6])\.\s*(.+)$', r'### \2', cleaned, flags=re.MULTILINE)
                                
                                # 3. Process line by line to handle lists and formatting properly with proper nesting
                                lines = cleaned.split('\n')
                                processed_lines = []
                                last_numbered_item = False  # Track if last item was a numbered list
                                in_numbered_context = False  # Track if we're in a numbered list context
                                
                                for line in lines:
                                    original_line = line
                                    line = line.rstrip()
                                    
                                    if not line.strip():
                                        processed_lines.append('')
                                        # Reset context on blank lines
                                        in_numbered_context = False
                                        last_numbered_item = False
                                        continue
                                    
                                    # Handle JIRA lists with proper hierarchical nesting
                                    if re.match(r'^(\s*)#{1,6}\s+', line):
                                        # Numbered list (# ## ### etc.) 
                                        hash_count = len(re.match(r'^(\s*)(#+)', line).group(2))
                                        content = re.sub(r'^(\s*)#+\s+(.+)$', r'\2', line)
                                        # Apply proper markdown indentation based on hash count
                                        markdown_indent = '    ' * (hash_count - 1)
                                        line = f"{markdown_indent}1. {content}"
                                        last_numbered_item = True
                                        in_numbered_context = True
                                    elif re.match(r'^(\s*)\*{2}\s+', line) and in_numbered_context:
                                        # Second-level bullet (**) - when in numbered context, these are sub-items
                                        content = re.sub(r'^(\s*)\*{2}\s+(.+)$', r'\2', line)
                                        # Sub-bullets under numbered items get proper indentation
                                        line = f"    - {content}"
                                        last_numbered_item = False
                                    elif re.match(r'^(\s*)\*{3,}\s+', line):
                                        # Third-level bullet (*** or more)
                                        content = re.sub(r'^(\s*)\*+\s+(.+)$', r'\2', line)
                                        # Third level = 8 spaces + dash
                                        line = f"        - {content}"
                                        last_numbered_item = False
                                    elif re.match(r'^(\s*)\*{2}\s+', line):
                                        # Second-level bullet (**) - when NOT in numbered context
                                        content = re.sub(r'^(\s*)\*{2}\s+(.+)$', r'\2', line)
                                        # Regular second level = 4 spaces + dash
                                        line = f"    - {content}"
                                        last_numbered_item = False
                                        in_numbered_context = False
                                    elif re.match(r'^(\s*)\*{1}\s+', line):
                                        # First-level bullet (*) 
                                        content = re.sub(r'^(\s*)\*{1}\s+(.+)$', r'\2', line)
                                        # First level = no indent + dash
                                        line = f"- {content}"
                                        last_numbered_item = False
                                        in_numbered_context = False
                                    else:
                                        # Non-list content - reset numbered context
                                        last_numbered_item = False
                                        # Only reset numbered context if this isn't just a continuation line
                                        if line.strip() and not line.startswith(' '):
                                            in_numbered_context = False
                                    
                                    # Now handle inline formatting (after list processing)
                                    # JIRA bold: *text* -> **text** (but only inline, not at start of line)
                                    # Use word boundaries and look for balanced pairs
                                    line = re.sub(r'(?<!\s)\*([^*\n]+?)\*(?!\s)', r'**\1**', line)
                                    
                                    # JIRA italic: _text_ -> *text*
                                    line = re.sub(r'(?<!\s)_([^_\n]+?)_(?!\s)', r'*\1*', line)
                                    
                                    processed_lines.append(line)
                                
                                result = '\n'.join(processed_lines)
                                
                                # 4. Convert JIRA links [text|url] to markdown [text](url)
                                result = re.sub(r'\[([^|\]]+)\|([^\]]+)\]', r'[\1](\2)', result)
                                
                                # 5. Clean up extra whitespace but preserve structure and intentional indentation
                                lines = result.split('\n')
                                cleaned_lines = []
                                for line in lines:
                                    # Don't strip leading whitespace for list items (preserve indentation)
                                    if re.match(r'^\s*[-\d]\s+', line):
                                        # This is a list item (bullet or numbered), preserve indentation
                                        rstripped = line.rstrip()  # Only remove trailing whitespace
                                        if rstripped:
                                            cleaned_lines.append(rstripped)
                                    else:
                                        # Regular content, safe to strip leading whitespace
                                        stripped = line.strip()
                                        if stripped:
                                            cleaned_lines.append(stripped)
                                        elif cleaned_lines and cleaned_lines[-1] != '':
                                            cleaned_lines.append('')  # Preserve paragraph breaks
                                
                                result = '\n'.join(cleaned_lines)
                                
                                # 6. Final cleanup - remove any remaining JIRA artifacts
                                result = re.sub(r'\{[^}]+\}', '', result)  # Remove any remaining {markup}
                                result = re.sub(r'\n\s*\n\s*\n+', '\n\n', result)  # Clean up multiple blank lines
                                
                                return result.strip()
                            
                            # Format dates nicely
                            def format_date(date_str):
                                """Format JIRA date string to be more readable"""
                                if not date_str:
                                    return "N/A"
                                try:
                                    from datetime import datetime
                                    # Parse ISO format and return a nicer format
                                    dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                                    return dt.strftime("%B %d, %Y at %I:%M %p")
                                except:
                                    return date_str
                            
                            # Handle missing/empty fields
                            def safe_field(value, default="N/A"):
                                return value if value and value.strip() else default
                            
                            # Clean the description
                            raw_description = issue_data.get('description', '')
                            
                            # Console logging for debugging
                            print(f"\n{'='*50}")
                            print(f"JIRA ISSUE DEBUG: {issue_data['key']}")
                            print(f"{'='*50}")
                            print(f"RAW DESCRIPTION:\n{raw_description}")
                            print(f"{'='*50}")
                            
                            clean_description = clean_jira_description(raw_description)
                            
                            print(f"CLEANED DESCRIPTION:\n{clean_description}")
                            print(f"{'='*50}\n")
                            
                            # Generate AI summary using MaaS model
                            ai_summary = ""
                            try:
                                summary_prompt = f"""Analyze this JIRA issue and provide a concise executive summary in 2-3 sentences:

**Issue:** {issue_data.get('summary', 'No summary available')}
**Status:** {safe_field(issue_data.get('status'))}
**Description:** {clean_description[:1000]}{'...' if len(clean_description) > 1000 else ''}

Focus on:
- What problem this addresses
- The proposed solution or request
- Current status/progress

Provide only the summary, no additional commentary."""

                                ai_summary = st.session_state.chatbot.model_client.generate_response(summary_prompt)
                                
                                # Clean up the AI response (remove any extra formatting)
                                ai_summary = ai_summary.strip()
                                if ai_summary.startswith('"') and ai_summary.endswith('"'):
                                    ai_summary = ai_summary[1:-1]
                                
                            except Exception as e:
                                logger.warning(f"Failed to generate AI summary: {e}")
                                ai_summary = "*AI summary generation failed*"
                            
                            # Add issue details to chat history with improved formatting (full description + AI summary)
                            issue_summary = f"""## JIRA Issue: {issue_data['key']}

### 🤖 AI Summary
{ai_summary}

### 📋 Summary
{issue_data.get('summary', 'No summary available')}

### 📊 Issue Details
| Field | Value |
|-------|-------|
| **Status** | {safe_field(issue_data.get('status'))} |
| **Assignee** | {safe_field(issue_data.get('assignee'))} |
| **Reporter** | {safe_field(issue_data.get('reporter'))} |
| **Priority** | {safe_field(issue_data.get('priority'))} |
| **Created** | {format_date(issue_data.get('created'))} |
| **Updated** | {format_date(issue_data.get('updated'))} |

### 📝 Full Description
{clean_description}

---
🔗 **[View in JIRA](https://issues.redhat.com/browse/{issue_data['key']})**"""
                            
                            # Add to chat history
                            st.session_state.chatbot.model_client.conversation_history.append({
                                'user': f"Show me details for JIRA issue {issue_key}",
                                'assistant': issue_summary
                            })
                    st.rerun()
                
                search_query = st.text_input("Search terms:", key="rfe_search")
                if st.button("🔍 Search Similar RFEs") and search_query:
                    with st.spinner("Searching for similar RFEs..."):
                        # Search for actual similar RFEs in JIRA
                        search_result = st.session_state.chatbot.atlassian_client.search_similar_rfes(search_query)
                        
                        if "error" in search_result:
                            st.error(f"Error: {search_result['error']}")
                        else:
                            results_data = search_result["result"]
                            if results_data["total"] > 0:
                                # Format search results
                                search_summary = f"**Similar RFEs Found ({results_data['total']} total):**\n\n"
                                for issue in results_data["issues"][:10]:  # Show first 10
                                    search_summary += f"• **{issue['key']}** - {issue['summary']}\n"
                                    search_summary += f"  Status: {issue['status']}, Assignee: {issue['assignee']}\n\n"
                                
                                # Add to chat history
                                st.session_state.chatbot.model_client.conversation_history.append({
                                    'user': f"Search for similar RFEs: {search_query}",
                                    'assistant': search_summary
                                })
                            else:
                                # Add no results message to chat
                                st.session_state.chatbot.model_client.conversation_history.append({
                                    'user': f"Search for similar RFEs: {search_query}",
                                    'assistant': f"No similar RFEs found for search terms: {search_query}"
                                                                 })
                    st.rerun()
            



if __name__ == "__main__":
    main()