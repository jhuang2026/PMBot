#!/bin/bash

# PM Chatbot Local Runner Script
set -e

echo "🚀 Starting PM Chatbot locally..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed or not in PATH"
    echo "Please install Python 3 and try again"
    exit 1
fi

echo "✅ Python 3 found: $(python3 --version)"

# Check if virtual environment exists and is valid
if [ ! -d "venv" ] || [ ! -f "venv/bin/python" ] && [ ! -f "venv/bin/python3" ]; then
    if [ -d "venv" ]; then
        echo "⚠️ Existing venv appears corrupted, removing..."
        rm -rf venv
    fi
    echo "📦 Creating virtual environment..."
    python3 -m venv venv
    if [ $? -eq 0 ]; then
        echo "✅ Virtual environment created successfully"
    else
        echo "❌ Failed to create virtual environment"
        exit 1
    fi
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Use local venv paths
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
    PIP_CMD="venv/bin/pip"
    echo "✅ Using venv Python"
elif [ -f "venv/bin/python3" ]; then
    PYTHON_CMD="venv/bin/python3" 
    PIP_CMD="venv/bin/pip3"
    echo "✅ Using venv Python3"
else
    echo "❌ Could not find Python in virtual environment"
    echo "Available files in venv/bin/:"
    ls -la venv/bin/ 2>/dev/null || echo "venv/bin/ directory not found"
    exit 1
fi

echo "✅ Using Python: $PYTHON_CMD"
echo "✅ Using Pip: $PIP_CMD"

# Check if dependencies are installed
echo "🔍 Checking dependencies..."
if ! $PYTHON_CMD -c "import streamlit, requests" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    
    # Check for SWIG before installing FAISS
    if ! command -v swig &> /dev/null; then
        echo "⚠️ SWIG not found. FAISS installation may fail."
        echo "To install SWIG:"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  Run: brew install swig"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            echo "  Ubuntu/Debian: sudo apt-get install swig build-essential"
            echo "  RHEL/CentOS: sudo yum install swig gcc-c++ python3-devel"
        fi
        echo "Continuing with installation..."
    fi
    
    # Use pip from virtual environment
    echo "Upgrading pip..."
    $PIP_CMD install --upgrade pip
    
    echo "Installing requirements..."
    if ! $PIP_CMD install -r config/requirements.txt; then
        echo "❌ Failed to install some dependencies"
        echo "If FAISS installation failed, try:"
        echo "  1. Install SWIG (see message above)"
        echo "  2. Run: $PIP_CMD install faiss-cpu --only-binary=faiss-cpu"
        echo "  3. Re-run this script"
        exit 1
    fi
    
    echo "✅ Dependencies installed"
else
    echo "✅ Dependencies already installed"
fi

# Check if .env file exists
if [ ! -f ".env" ]; then
    echo "⚠️ .env file not found."
    
    if [ -f ".env.template" ]; then
        echo "📝 Copying .env.template to .env..."
        cp .env.template .env
        echo "✅ Created .env from template"
        echo ""
        echo "🔧 IMPORTANT: Edit .env with your actual credentials:"
        echo "   1. Add your MaaS API keys and endpoints"
        echo "   2. Add your JIRA personal access token"
        echo "   3. (Optional) Add Confluence credentials"
        echo ""
        echo "📚 See docs/README.md for detailed instructions"
        echo ""
    else
        echo "❌ Neither .env nor .env.template found"
        echo "� Please copy .env.template to .env and configure it"
        echo "📚 See docs/README.md for setup instructions"
        exit 1
    fi
fi

echo ""
echo "🎉 Setup complete! Starting the application..."
echo "🌐 The app will be available at: http://localhost:8501"
echo ""
echo "💡 Tips:"
echo " - Edit .env with your MaaS and Atlassian credentials for full functionality"
echo " - Press Ctrl+C to stop the application"
echo " - Configure your MaaS endpoint in the .env file"
echo ""

# Verify Python path one more time
echo "🔍 Final verification:"
echo "  Python executable: $PYTHON_CMD"
echo "  Python version: $($PYTHON_CMD --version 2>&1)"
echo "  Virtual environment: ./venv"
echo ""

# Start the Streamlit application
echo "🚀 Launching Streamlit..."
$PYTHON_CMD -m streamlit run pm_chatbot_main.py --server.address=0.0.0.0 --server.port=8501