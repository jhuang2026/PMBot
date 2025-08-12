# PMBot - Product Manager Assistant 🤖

A sophisticated AI-powered chatbot designed to assist Product Managers with RFE (Request for Enhancement) creation, validation, and JIRA integration. Built for Red Hat Enterprise context but adaptable to other organizations. Features Streamlit frontend, FastAPI backend, and deployed on OpenShift.

## 🌐 Live Demo

**Try it now - no setup required!** *(Live access available until Friday, August 15th, 2025)*

- 🎯 **Streamlit Web App**: https://pm-chatbot.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com
- 🔧 **API Endpoint**: https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com
- 📚 **API Documentation**: https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/docs

## ✨ Key Features

- **🎯 RFE Generation**: Create well-structured Request for Enhancement documents
- **📋 Template Validation**: Ensure RFEs follow proper guidelines and formats
- **🔗 JIRA Integration**: Seamlessly create and manage JIRA tickets
- **📚 Document Search**: Query Red Hat AI documentation with vector-based search
- **🌐 REST API**: Programmable access to all functionality
- **🤖 MCP Support**: Model Context Protocol integration for AI agents and tools
- **☁️ Cloud Ready**: Containerized and deployed on OpenShift

## 🚀 Getting Started

### Option 1: Use the Web Interface (Recommended)
1. Visit the **[Streamlit Web App](https://pm-chatbot.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com)**
2. Start chatting with the PM assistant
3. Ask for help with RFE creation, JIRA integration, or Red Hat AI documentation

### Option 2: Use the REST API
1. Check out the **[API Documentation](https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/docs)**
2. Test endpoints directly in the browser

### Option 3: MCP Integration (For AI Agents & Tools)

**Model Context Protocol (MCP)** allows AI agents and tools to interact with PMBot programmatically. Perfect for integrating with Claude Desktop, VS Code extensions, or custom AI workflows.

#### Quick MCP Setup
Add this to your MCP client configuration (e.g., Claude Desktop's `mcp.json`):

```json
{
  "pm-chatbot-production": {
    "command": "mcp-proxy",
    "args": [
      "https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/mcp"
    ],
    "env": {
      "AUTHORIZATION": "Bearer pmbot-production-token"
    }
  }
}
```

#### Available MCP Tools
- `mcp_rfe_generate` (POST /mcp/rfe/generate) - Generate RFEs from natural language requests
- `mcp_rfe_validate` (POST /mcp/rfe/validate) - Validate RFE content against guidelines
- `mcp_search_documents` (POST /mcp/documents/search) - Search Red Hat AI documentation
- `mcp_get_models` (GET /mcp/models) - List available AI models
- `mcp_create_jira_issue` (POST /mcp/jira/issues) - Create JIRA tickets
- `mcp_update_jira_issue` (PUT /mcp/jira/issues/{issue_key}) - Update existing JIRA tickets

**Note**: For direct API access, use the `/api/v1/` endpoints shown in the API examples below.

#### MCP Usage Examples
Once configured, AI agents can use natural language like:
- *"Generate an RFE for improving API rate limiting"*
- *"Validate this RFE draft against Red Hat guidelines"*
- *"Search for Red Hat AI installation requirements"*
- *"What models are available for RFE generation?"*
- *"Create a JIRA ticket for this enhancement request"*
- *"Update JIRA issue RHOAI-123 with additional details"*

**MCP Endpoint**: https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/mcp

## 🛠️ API Usage Examples

### Generate an RFE
```bash
# With authentication token (required for deployed API)
curl -X POST "https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/api/v1/rfe/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer pmbot-production-token" \
  --max-time 120 \
  -d '{
    "prompt": "Create an RFE for improving AI model performance monitoring",
    "context": "Red Hat AI platform needs better monitoring capabilities for deployed models",
    "selected_product": "Red Hat AI"
  }'
```

### Search Documentation
```bash
curl -X POST "https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/mcp/documents/search" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer pmbot-production-token" \
  -d '{
    "query": "Red Hat AI installation requirements",
    "limit": 5
  }'
```

## 🏗️ Architecture

```
            ┌─────────────────┐
            │   OpenShift     │
        ┌── │   Deployment    │ ──┐
        │   │                 │   │
        ▼   └─────────────────┘   ▼
┌─────────────────┐    ┌─────────────────┐    
│   Streamlit     │    │    FastAPI      │    
│   Frontend      │◄──►│    Backend      │
│                 │    │  + MCP Server   │    
└─────────────────┘    └─────────────────┘\    
         │                       │         \            
         ▼                       ▼          \           
┌─────────────────┐    ┌─────────────────┐   \┌─────────────────┐
│   User Chat     │    │  Vector DB      │    │   JIRA API      │
│   Interface     │◄──►│  (FAISS)        │◄──►│   Integration   │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       
         ▼                       ▼                       
┌─────────────────┐    ┌─────────────────┐               
│  MCP Clients    │    │   AI Agents     │               
│ (Claude, Tools) │    │  & Extensions   │               
└─────────────────┘    └─────────────────┘               
```

## 📁 Project Structure

```
PMBot/
├── 🎯 Core Components
│   ├── pm_chatbot_main.py      # Streamlit frontend application
│   ├── api_server.py           # FastAPI backend server
│   ├── atlassian_client.py     # JIRA/Confluence integration
│   ├── rfe_manager.py          # RFE creation and validation
│   ├── document_processor.py   # Document processing and indexing
│   ├── vector_database.py      # Vector database operations
│   └── auth.py                 # Authentication utilities
│
├── 📚 Documentation & Data
│   ├── documents/              # Source documentation (PDFs)
│   ├── document_cache/         # Processed document cache (JSON)
│   ├── vector_db/              # FAISS vector database files
│   └── docs/                   # Project documentation
│       └── RFE_Issue_Description_Guidelines.md
│
├── ☁️ Deployment & Infrastructure
│   ├── deployment/
│   │   ├── docker/             # Container definitions
│   │   ├── openshift/          # OpenShift deployment configs
│   │   └── scripts/            # Deployment scripts
│   ├── .github/                # GitHub Actions workflows
│   └── deploy-to-cluster.sh    # Main deployment script
│
├── 🔧 Configuration
│   ├── config/
│   │   ├── requirements.txt        # Core Python dependencies
│   │   ├── requirements.api.txt    # API-specific dependencies
│   │   ├── requirements.full.txt   # Complete dependency list
│   │   └── nginx.conf              # Nginx configuration
│   ├── .env.template               # Environment variables template
│   └── .streamlit/                 # Streamlit configuration
│
└── 🛠️ Utilities & Scripts
    ├── scripts/
    │   └── setup-github-secrets.sh # GitHub secrets setup
    └── utils/
        ├── local-app.sh            # Local Streamlit app launcher
        └── local-backend.sh        # Local API server launcher
```

## 🔧 Local Development Setup

### Prerequisites
- Python 3.11+ installed
- Git installed
- JIRA account with personal access token
- MaaS (Model-as-a-Service) API credentials

### System Dependencies

**macOS:**
```bash
# Install SWIG (required for FAISS vector database)
brew install swig
```

**Ubuntu/Debian:**
```bash
# Install SWIG and build tools
sudo apt-get update
sudo apt-get install swig build-essential
```

**RHEL/CentOS/Fedora:**
```bash
# Install SWIG and development tools
sudo yum install swig gcc-c++ python3-devel
# OR for newer versions:
sudo dnf install swig gcc-c++ python3-devel
```

### 🚀 Quick Start (5 minutes - Recommended!)

#### Step 1: Clone & Setup
```bash
# Clone the repository
git clone https://github.com/jhuang2026/PMBot.git
cd PMBot
```

#### Step 2: Configure Environment
```bash
# Copy the template
cp .env.template .env

# Edit with your credentials
nano .env  # or use your preferred editor
```

#### Step 3: Get Your Credentials

**JIRA Personal Access Token**
1. Go to https://issues.redhat.com/secure/ViewProfile.jspa?selectedTab=com.atlassian.pats.pats-plugin:jira-user-personal-access-tokens
2. Create a new token
3. Copy it to `JIRA_PERSONAL_TOKEN` in your `.env` file

**MaaS API Credentials**
For Red Hat users, visit the [Red Hat MaaS Platform](https://maas.apps.prod.rhoai.rh-aiservices-bu.com/) to get your credentials.

Contact your AI service provider for:
- API Key
- Base URL endpoint  
- Model name

Add at least ONE model configuration to your `.env` file.

#### Step 4: Run the Application
```bash
# Start the application (installs dependencies automatically)
./utils/local-app.sh

# Note: If you get FAISS installation errors, install SWIG first:
# macOS: brew install swig
# Ubuntu: sudo apt-get install swig build-essential
# RHEL/CentOS: sudo yum install swig gcc-c++ python3-devel
```

The app will be available at: http://localhost:8501

#### Step 5: (Optional) Start API Server
```bash
# In a new terminal, start the API server
./utils/local-backend.sh

# Note: This installs additional API dependencies from requirements.api.txt
```

API will be available at: http://localhost:8000  
API docs at: http://localhost:8000/docs

### Environment Variables Quick Reference

#### Required Variables
```bash
# Minimum required for basic functionality
MAAS_PHI_4_API_KEY=your_api_key
MAAS_PHI_4_BASE_URL=https://your-endpoint.com/v1
MAAS_PHI_4_MODEL_NAME=microsoft/phi-4

JIRA_URL=https://issues.redhat.com/
JIRA_PERSONAL_TOKEN=your_token
```

## 🚀 Production Deployment

### Manual Deployment (Foundation)

#### Prerequisites for Deployment
1. **OpenShift/Kubernetes cluster** with admin access
2. **Container registry access** (Quay.io recommended)
3. **Environment configuration** (see below)

#### Container Registry Setup

⚠️ **IMPORTANT REGISTRY NOTICE**: This repository is currently configured to use `quay.io/rh-ee-jashuang` as the default registry. **You should set up your own registry** to avoid pushing images to someone else's account.

**Option 1: Quay.io (Recommended)**
```bash
# 1. Create account at https://quay.io
# 2. Create repository: quay.io/your-username/pm-chatbot-streamlit
# 3. Create repository: quay.io/your-username/pm-chatbot-api
# 4. Make repositories public for easier access
# 5. Login locally
podman login quay.io
```

**Option 2: Docker Hub**
```bash
# 1. Create account at https://hub.docker.com
# 2. Create repositories for streamlit and api images
# 3. Login locally
podman login docker.io
```

#### Using the Deploy Script

The `deploy-to-cluster.sh` script is a comprehensive, intelligent deployment tool that handles everything automatically. Perfect for first-time users!

⚠️ **IMPORTANT**: By default, this script is configured to use the `quay.io/rh-ee-jashuang` registry. You should change this to your own registry before deploying to avoid pushing to someone else's container registry.

**Basic Usage (Simplest):**
```bash
# Clone the repository
git clone https://github.com/jhuang2026/PMBot.git
cd PMBot

# Configure your environment
cp .env.template .env
# Edit .env with your credentials (see Step 3 above for credential sources)

# IMPORTANT: Use your own registry (recommended)
./deploy-to-cluster.sh -r quay.io/your-username

# OR: Deploy with default registry (uses rh-ee-jashuang - not recommended)
./deploy-to-cluster.sh
```

**Advanced Usage Options:**
```bash
# Deploy to a different cluster (specify API URL)
./deploy-to-cluster.sh -a https://api.your-cluster.com:6443

# Use your own container registry
./deploy-to-cluster.sh -r quay.io/your-username

# Deploy to a custom namespace
./deploy-to-cluster.sh -n my-custom-namespace

# Combine multiple options
./deploy-to-cluster.sh -a https://api.new-cluster.com:6443 -r quay.io/myorg -n production

# See all available options
./deploy-to-cluster.sh --help
```

**🎯 What the Script Does Automatically:**

1. **🔍 Cluster Detection** - Works with both new and existing OpenShift clusters
2. **🏗️ Smart Building** - Only rebuilds images when source code changes (saves time!)
3. **📦 Container Management** - Handles Podman setup, registry login, and image pushing
4. **🔐 Security Setup** - Creates all required secrets from your `.env` file
5. **🚀 Deployment** - Applies all OpenShift configurations and waits for readiness
6. **📊 Cache Upload** - Uploads pre-built RAG cache for faster startup
7. **✅ Verification** - Checks all services and provides final URLs

**📋 First-Time User Checklist:**

Before running the script, ensure you have:
- ✅ **OpenShift cluster access** (login with `oc login`)
- ✅ **Container registry account** (Quay.io or Docker Hub)
- ✅ **Podman installed** (script will try to start it automatically)
- ✅ **Environment configured** (`.env` file with your credentials)

**⚡ Performance Features:**

The script includes several optimizations for faster deployments:
- **Smart caching** - Remembers previous deployments and skips unchanged components
- **Parallel operations** - Builds and deploys multiple components simultaneously  
- **Layer reuse** - Docker layers are cached between builds
- **Incremental updates** - Only updates what actually changed

**🔧 Troubleshooting:**

If deployment fails:
```bash
# Check your cluster connection
oc whoami
oc get nodes

# Verify Podman is working  
podman info

# Check container registry login
podman login quay.io  # or your registry

# See detailed script help
./deploy-to-cluster.sh --help
```

**🌐 Deployment Scenarios:**

```bash
# Scenario 1: RECOMMENDED - Deploy with your own registry
./deploy-to-cluster.sh -r quay.io/your-username

# Scenario 2: Deploy to a different OpenShift cluster with your registry
./deploy-to-cluster.sh -a https://api.cluster-abc.sandbox.com:6443 -r quay.io/your-username

# Scenario 3: Use Docker Hub instead of Quay
./deploy-to-cluster.sh -r docker.io/your-username

# Scenario 4: Deploy to a custom namespace with your registry
./deploy-to-cluster.sh -r quay.io/your-username -n my-custom-namespace

# Scenario 5: Production deployment (custom cluster + your registry + namespace)
./deploy-to-cluster.sh \
  -a https://api.prod-cluster.company.com:6443 \
  -r quay.io/your-company \
  -n pmbot-production

# Scenario 6: Development environment
./deploy-to-cluster.sh \
  -a https://api.dev-cluster.sandbox.com:6443 \
  -r quay.io/dev-team \
  -n pmbot-dev

# ⚠️ NOT RECOMMENDED: Deploy with default registry (uses rh-ee-jashuang)
# ./deploy-to-cluster.sh
```

**💡 Pro Tips:**
- The script remembers your last deployment settings for faster re-deployments
- Use `-a` flag to easily switch between different OpenShift clusters
- Each deployment creates cache files to speed up subsequent deployments
- The script works with any OpenShift-compatible cluster (OKD, RHOKS, etc.)

### GitHub Actions Deployment (Automated)

This repository includes automated GitHub Actions workflows for building and deploying to OpenShift. This builds on the manual deployment foundation above. **IMPORTANT**: You must set up GitHub Secrets before deploying.

## 🔐 Security Setup for GitHub Deployment

### ⚠️ CRITICAL: Setting Up GitHub Secrets

This repository requires sensitive credentials (API keys, tokens) that must NOT be stored in the code. Instead, they should be configured as GitHub Secrets for secure deployment.

#### Step 1: Navigate to Repository Secrets

1. Go to your GitHub repository
2. Click **Settings** (in the repository menu)
3. In the left sidebar, click **Secrets and variables** → **Actions**
4. Click **New repository secret**

#### Step 2: Add Required Secrets

You need to add the following secrets (use the values from your `.env` file):

##### JIRA Configuration
- `JIRA_URL` - Your JIRA instance URL (e.g., `https://issues.redhat.com/`)
- `JIRA_PERSONAL_TOKEN` - Your personal JIRA API token

##### MaaS Model Configuration
For each model you want to use, add these secrets:

**DeepSeek R1 Qwen 14B:**
- `MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY`
- `MAAS_DEEPSEEK_R1_QWEN_14B_BASE_URL`
- `MAAS_DEEPSEEK_R1_QWEN_14B_MODEL_NAME`

**Phi-4:**
- `MAAS_PHI_4_API_KEY`
- `MAAS_PHI_4_BASE_URL`
- `MAAS_PHI_4_MODEL_NAME`

**Granite 3.3 8B Instruct:**
- `MAAS_GRANITE_3_3_8B_INSTRUCT_API_KEY`
- `MAAS_GRANITE_3_3_8B_INSTRUCT_BASE_URL`
- `MAAS_GRANITE_3_3_8B_INSTRUCT_MODEL_NAME`

**Llama 4 Scout 17B:**
- `MAAS_LLAMA_4_SCOUT_17B_API_KEY`
- `MAAS_LLAMA_4_SCOUT_17B_BASE_URL`
- `MAAS_LLAMA_4_SCOUT_17B_MODEL_NAME`

**Mistral Small 24B:**
- `MAAS_MISTRAL_SMALL_24B_API_KEY`
- `MAAS_MISTRAL_SMALL_24B_BASE_URL`
- `MAAS_MISTRAL_SMALL_24B_MODEL_NAME`

#### Step 3: Automated Setup (Recommended)

Use the provided script to set up all secrets easily:

```bash
# Install GitHub CLI if not already installed
# See: https://cli.github.com/

# Authenticate with GitHub
gh auth login

# Run the setup script
./scripts/setup-github-secrets.sh
```

#### Step 4: Verify Secrets

After adding all secrets:
1. The GitHub Actions workflow will automatically use them during deployment
2. Check deployment logs to ensure no authentication errors
3. Visit your deployed application to verify it's working

### Security Best Practices

1. **Never commit credentials** to version control
2. **Rotate API keys regularly**
3. **Use least-privilege access** for service accounts
4. **Monitor secret usage** in logs and audit trails
5. **Remove unused secrets** promptly

### Troubleshooting Deployment

If deployment fails with authentication errors:
1. Verify all required secrets are added to GitHub
2. Check secret names match exactly (case-sensitive)  
3. Ensure API keys are valid and not expired
4. Check base URLs are accessible from your deployment environment
5. Review GitHub Actions logs for specific error messages

#### Deploy to OpenShift
Once GitHub Secrets are configured, simply push to the main branch:

```bash
git add .
git commit -m "Configure deployment"
git push origin main
```

The GitHub Actions workflow will automatically:
- Build container images
- Push to your container registry
- Deploy to OpenShift
- Set up networking and routes

## 🐛 Troubleshooting

### Common Issues

**"No MaaS models configured"**
- Check that you have at least one complete MaaS model configuration (API_KEY, BASE_URL, MODEL_NAME)
- Verify environment variables are loaded: `echo $MAAS_PHI_4_API_KEY`

**"JIRA connection failed"**
- Verify JIRA_URL and JIRA_PERSONAL_TOKEN are correct
- Test JIRA token: https://issues.redhat.com/rest/api/2/myself
- Check token permissions in JIRA settings

**"Module not found" errors**
- Ensure you're in the virtual environment: `source venv/bin/activate`
- Reinstall dependencies: `pip install -r config/requirements.txt`
- Try using the automated setup: `./utils/local-app.sh`

**FAISS installation issues**
- **Error: Microsoft Visual C++ 14.0 is required** (Windows): Install Visual Studio Build Tools
- **Error: swig executable not found** (All platforms): Install SWIG first
  - macOS: `brew install swig`
  - Ubuntu/Debian: `sudo apt-get install swig build-essential`
  - RHEL/CentOS: `sudo yum install swig gcc-c++ python3-devel`

**GitHub Actions Deployment Failures**
- Verify all required GitHub Secrets are set (see Security Setup section)
- Check GitHub Actions logs for specific error messages
- Ensure secret names match exactly (case-sensitive)
- Verify API keys are valid and not expired

## 🔐 Security Notes

### For Production Deployment
- **Never commit credentials** to version control
- **Use GitHub Secrets** for all sensitive values in CI/CD
- **Rotate API keys regularly**
- **Use least-privilege access** for service accounts
- **Monitor secret usage** in logs and audit trails

### For Development
- Keep credentials in `.env` file (gitignored)
- Use development-specific API keys when possible
- Regularly update dependencies for security patches

## 🤝 Common Use Cases

1. **Create an RFE**: Use the chat interface to describe your enhancement request
2. **Validate RFE Format**: Check if your RFE follows proper guidelines
3. **Search Documentation**: Find relevant Red Hat AI documentation
4. **JIRA Integration**: Create and manage JIRA tickets directly
5. **API Automation**: Integrate RFE creation into your development workflow
6. **MCP Integration**: Connect AI agents (Claude Desktop, VS Code) for automated workflows

## 🔐 Authentication

### Web Interface
- **Streamlit App**: No authentication required - visit the web interface directly
- **Interactive Testing**: Use the web interface for easy testing without tokens

### API Access
- **Production API**: Requires authentication token in header: `Authorization: Bearer pmbot-production-token`
- **Local Development**: May not require authentication depending on configuration
- **Token Format**: Use `Bearer` followed by your token

### Getting Tokens
- **Contact**: Repository maintainer for production API tokens
- **Local Setup**: Configure your own tokens in `.env` file for local development
- **JIRA Integration**: Requires separate JIRA personal access token

---

**Ready to get started?** Try the [live demo](https://pm-chatbot.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com) or explore the [API](https://pm-chatbot-api.apps.cluster-znvdr.znvdr.sandbox203.opentlc.com/docs)! 🚀