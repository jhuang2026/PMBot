#!/bin/bash

# 🚀 Local API Server Runner
# ========================
# This script runs the PM Chatbot API server locally for development

set -e

echo "🚀 Starting PM Chatbot API Server locally..."
echo "========================================"

# Check if Python environment is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 is not installed or not in PATH"
    exit 1
fi

# Check if required dependencies are installed
echo "🔍 Checking dependencies..."
if ! python3 -c "import streamlit, requests" &> /dev/null; then
    echo "❌ Main dependencies not found. Please run ./utils/local-app.sh first"
    echo "💡 This will install the main requirements.txt"
    exit 1
fi

if ! python3 -c "import fastapi, uvicorn" &> /dev/null; then
    echo "📦 Installing API dependencies..."
    pip install -r config/requirements.api.txt
    echo "✅ API dependencies installed"
else
    echo "✅ API dependencies already installed"
fi

# Check for .env file
if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found."
    if [ -f ".env.template" ]; then
        echo "📝 Please copy .env.template to .env and configure it first"
        echo "💡 Run: cp .env.template .env"
        echo "📚 See docs/README.md for detailed instructions"
    else
        echo "❌ Neither .env nor .env.template found"
        echo "📚 Please check docs/README.md for configuration instructions"
    fi
    exit 1
fi

# Load environment variables from .env file
set -a  # automatically export all variables
source .env
set +a  # stop auto-exporting

# Set environment variables for local development
export ENVIRONMENT=development
export AUTH_METHOD=simple
export JIRA_URL=${JIRA_URL:-"https://issues.redhat.com/"}
export JIRA_PERSONAL_TOKEN=${JIRA_PERSONAL_TOKEN:-""}

# MAAS configuration (loaded from .env)
echo "🔍 Checking MaaS configuration..."
MODEL_COUNT=0

if [ -n "$MAAS_PHI_4_API_KEY" ] && [ -n "$MAAS_PHI_4_BASE_URL" ] && [ -n "$MAAS_PHI_4_MODEL_NAME" ]; then
    echo "✅ Phi-4 model configured (recommended)"
    MODEL_COUNT=$((MODEL_COUNT + 1))
fi

if [ -n "$MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY" ] && [ -n "$MAAS_DEEPSEEK_R1_QWEN_14B_BASE_URL" ] && [ -n "$MAAS_DEEPSEEK_R1_QWEN_14B_MODEL_NAME" ]; then
    echo "✅ DeepSeek model configured"
    MODEL_COUNT=$((MODEL_COUNT + 1))
fi

if [ -n "$MAAS_GRANITE_3_3_8B_INSTRUCT_API_KEY" ] && [ -n "$MAAS_GRANITE_3_3_8B_INSTRUCT_BASE_URL" ] && [ -n "$MAAS_GRANITE_3_3_8B_INSTRUCT_MODEL_NAME" ]; then
    echo "✅ Granite model configured"
    MODEL_COUNT=$((MODEL_COUNT + 1))
fi

if [ -n "$MAAS_LLAMA_4_SCOUT_17B_API_KEY" ] && [ -n "$MAAS_LLAMA_4_SCOUT_17B_BASE_URL" ] && [ -n "$MAAS_LLAMA_4_SCOUT_17B_MODEL_NAME" ]; then
    echo "✅ Llama 4 Scout model configured"
    MODEL_COUNT=$((MODEL_COUNT + 1))
fi

if [ -n "$MAAS_MISTRAL_SMALL_24B_API_KEY" ] && [ -n "$MAAS_MISTRAL_SMALL_24B_BASE_URL" ] && [ -n "$MAAS_MISTRAL_SMALL_24B_MODEL_NAME" ]; then
    echo "✅ Mistral Small model configured"
    MODEL_COUNT=$((MODEL_COUNT + 1))
fi

if [ $MODEL_COUNT -eq 0 ]; then
    echo "❌ No MaaS models configured!"
    echo "💡 Please configure at least one model in your .env file"
    echo "📝 Example: Set MAAS_PHI_4_API_KEY, MAAS_PHI_4_BASE_URL, and MAAS_PHI_4_MODEL_NAME"
    exit 1
fi

echo "🎯 Total models configured: $MODEL_COUNT"

echo "🔧 Environment: $ENVIRONMENT"
echo "🔗 API will be available at: http://localhost:8000"
echo "📊 API docs at: http://localhost:8000/docs"
echo "🤖 MCP endpoint at: http://localhost:8000/mcp"
echo ""

# Start the API server
echo "▶️ Starting API server..."
uvicorn api_server:app --host 0.0.0.0 --port 8000 --reload 