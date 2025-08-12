#!/bin/bash

# GitHub Secrets Setup Helper Script
# This script helps you set up GitHub repository secrets for secure deployment
#
# Features:
# - Auto-detects values from .env file (if present)
# - Offers bulk setup for all detected secrets
# - Interactive confirmation for each secret
# - Skips existing secrets (with option to update)
#
# Usage:
#   ./scripts/setup-github-secrets.sh
#
# Prerequisites:
#   - GitHub CLI (gh) installed and authenticated
#   - .env file with your credentials (optional, but recommended)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🔐 GitHub Secrets Setup Helper${NC}"
echo -e "${BLUE}=================================${NC}"
echo ""

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}❌ GitHub CLI (gh) is not installed.${NC}"
    echo "Please install it from: https://cli.github.com/"
    echo "Then run: gh auth login"
    exit 1
fi

# Check if user is authenticated
if ! gh auth status &> /dev/null; then
    echo -e "${RED}❌ Not authenticated with GitHub CLI.${NC}"
    echo "Please run: gh auth login"
    exit 1
fi

echo -e "${GREEN}✅ GitHub CLI is installed and authenticated${NC}"
echo ""

# Get repository info
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
echo -e "${BLUE}Repository: ${REPO}${NC}"
echo ""

# Check for .env file and load values
ENV_FILE=".env"

# Function to get value from .env file
get_env_value() {
    local key="$1"
    if [[ -f "$ENV_FILE" ]]; then
        grep "^${key}=" "$ENV_FILE" | cut -d'=' -f2- | xargs | sed 's/^["'"'"']//' | sed 's/["'"'"']$//'
    fi
}

if [[ -f "$ENV_FILE" ]]; then
    echo -e "${GREEN}✅ Found .env file - loading values automatically${NC}"
    echo ""
    
    # Count non-comment, non-empty lines
    env_count=$(grep -v "^#" "$ENV_FILE" | grep -v "^$" | wc -l | xargs)
    echo -e "${BLUE}📋 Found $env_count configuration lines in .env file${NC}"
    
    # Show some examples of loaded values (first 20 chars for security)
    echo -e "${BLUE}Examples of detected values:${NC}"
    for key in JIRA_URL MAAS_PHI_4_API_KEY MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY; do
        value=$(get_env_value "$key")
        if [[ -n "$value" ]]; then
            echo "  $key: ${value:0:20}..."
        fi
    done
    echo ""
else
    echo -e "${YELLOW}⚠️ No .env file found - you'll need to enter values manually${NC}"
    echo "💡 Tip: Copy .env.template to .env and fill in your values first"
    echo ""
fi

# Function to set a secret
set_secret() {
    local secret_name=$1
    local secret_description=$2
    local secret_value=""
    local auto_detected_value=""
    
    echo -e "${YELLOW}Setting up: ${secret_name}${NC}"
    echo "Description: ${secret_description}"
    
    # Check if secret already exists
    if gh secret list | grep -q "^${secret_name}"; then
        echo -e "${YELLOW}⚠️ Secret '${secret_name}' already exists.${NC}"
        read -p "Do you want to update it? (y/N): " update_choice
        if [[ ! $update_choice =~ ^[Yy]$ ]]; then
            echo "Skipping ${secret_name}"
            echo ""
            return
        fi
    fi
    
    # Try to get value from .env file
    auto_detected_value=$(get_env_value "$secret_name")
    
    if [[ -n "$auto_detected_value" ]]; then
        echo -e "${GREEN}🔍 Auto-detected from .env file${NC}"
        echo "Value: ${auto_detected_value:0:20}..." # Show first 20 chars for verification
        read -p "Use this value? (Y/n): " use_auto
        
        if [[ ! $use_auto =~ ^[Nn]$ ]]; then
            secret_value="$auto_detected_value"
        else
            read -s -p "Enter custom value for ${secret_name}: " secret_value
            echo ""
        fi
    else
        echo -e "${YELLOW}⚠️ Not found in .env file${NC}"
        read -s -p "Enter value for ${secret_name}: " secret_value
        echo ""
    fi
    
    if [[ -z "$secret_value" ]]; then
        echo -e "${RED}❌ Empty value provided. Skipping.${NC}"
        echo ""
        return
    fi
    
    if gh secret set "$secret_name" --body "$secret_value"; then
        echo -e "${GREEN}✅ Secret '${secret_name}' set successfully${NC}"
    else
        echo -e "${RED}❌ Failed to set secret '${secret_name}'${NC}"
    fi
    echo ""
}

echo -e "${BLUE}🚀 Starting secrets setup...${NC}"
echo ""

# Check if we can do bulk auto-setup
required_secrets=(
    "JIRA_URL"
    "JIRA_PERSONAL_TOKEN"
    "MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY"
    "MAAS_DEEPSEEK_R1_QWEN_14B_BASE_URL"
    "MAAS_DEEPSEEK_R1_QWEN_14B_MODEL_NAME"
    "MAAS_PHI_4_API_KEY"
    "MAAS_PHI_4_BASE_URL"
    "MAAS_PHI_4_MODEL_NAME"
    "MAAS_GRANITE_3_3_8B_INSTRUCT_API_KEY"
    "MAAS_GRANITE_3_3_8B_INSTRUCT_BASE_URL"
    "MAAS_GRANITE_3_3_8B_INSTRUCT_MODEL_NAME"
    "MAAS_LLAMA_4_SCOUT_17B_API_KEY"
    "MAAS_LLAMA_4_SCOUT_17B_BASE_URL"
    "MAAS_LLAMA_4_SCOUT_17B_MODEL_NAME"
    "MAAS_MISTRAL_SMALL_24B_API_KEY"
    "MAAS_MISTRAL_SMALL_24B_BASE_URL"
    "MAAS_MISTRAL_SMALL_24B_MODEL_NAME"
)

# Count how many secrets we have from .env
found_count=0
for secret in "${required_secrets[@]}"; do
    value=$(get_env_value "$secret")
    if [[ -n "$value" ]]; then
        ((found_count++))
    fi
done

if [[ $found_count -gt 0 ]]; then
    echo -e "${GREEN}🎯 Found $found_count out of ${#required_secrets[@]} required secrets in .env file${NC}"
    
    if [[ $found_count -ge 10 ]]; then
        echo ""
        read -p "🚀 Auto-setup all detected secrets? This will set up secrets without individual confirmation (y/N): " bulk_setup
        
        if [[ $bulk_setup =~ ^[Yy]$ ]]; then
            echo -e "${BLUE}🔄 Setting up all detected secrets automatically...${NC}"
            echo ""
            
            for secret in "${required_secrets[@]}"; do
                value=$(get_env_value "$secret")
                if [[ -n "$value" ]]; then
                    if gh secret set "$secret" --body "$value"; then
                        echo -e "${GREEN}✅ $secret${NC}"
                    else
                        echo -e "${RED}❌ Failed: $secret${NC}"
                    fi
                fi
            done
            
            echo ""
            echo -e "${GREEN}🎉 Bulk setup completed!${NC}"
            echo -e "${YELLOW}⚠️ Missing secrets (if any) will need to be set manually in GitHub${NC}"
            echo "You can view all secrets at: https://github.com/${REPO}/settings/secrets/actions"
            exit 0
        fi
    fi
fi

echo -e "${BLUE}📝 Setting up secrets individually (you can confirm each one)...${NC}"
echo ""

# JIRA Configuration
echo -e "${BLUE}--- JIRA Configuration ---${NC}"
set_secret "JIRA_URL" "JIRA instance URL (e.g., https://issues.redhat.com/)"
set_secret "JIRA_PERSONAL_TOKEN" "Personal JIRA API token"

echo -e "${BLUE}--- MaaS Model Configurations ---${NC}"

# DeepSeek R1 Qwen 14B
echo -e "${BLUE}DeepSeek R1 Qwen 14B:${NC}"
set_secret "MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY" "API key for DeepSeek R1 Qwen 14B model"
set_secret "MAAS_DEEPSEEK_R1_QWEN_14B_BASE_URL" "Base URL for DeepSeek R1 Qwen 14B endpoint"
set_secret "MAAS_DEEPSEEK_R1_QWEN_14B_MODEL_NAME" "Model name for DeepSeek R1 Qwen 14B"

# Phi-4
echo -e "${BLUE}Phi-4:${NC}"
set_secret "MAAS_PHI_4_API_KEY" "API key for Phi-4 model"
set_secret "MAAS_PHI_4_BASE_URL" "Base URL for Phi-4 endpoint"
set_secret "MAAS_PHI_4_MODEL_NAME" "Model name for Phi-4"

# Granite 3.3 8B Instruct
echo -e "${BLUE}Granite 3.3 8B Instruct:${NC}"
set_secret "MAAS_GRANITE_3_3_8B_INSTRUCT_API_KEY" "API key for Granite 3.3 8B Instruct model"
set_secret "MAAS_GRANITE_3_3_8B_INSTRUCT_BASE_URL" "Base URL for Granite 3.3 8B Instruct endpoint"
set_secret "MAAS_GRANITE_3_3_8B_INSTRUCT_MODEL_NAME" "Model name for Granite 3.3 8B Instruct"

# Llama 4 Scout 17B
echo -e "${BLUE}Llama 4 Scout 17B:${NC}"
set_secret "MAAS_LLAMA_4_SCOUT_17B_API_KEY" "API key for Llama 4 Scout 17B model"
set_secret "MAAS_LLAMA_4_SCOUT_17B_BASE_URL" "Base URL for Llama 4 Scout 17B endpoint"
set_secret "MAAS_LLAMA_4_SCOUT_17B_MODEL_NAME" "Model name for Llama 4 Scout 17B"

# Mistral Small 24B
echo -e "${BLUE}Mistral Small 24B:${NC}"
set_secret "MAAS_MISTRAL_SMALL_24B_API_KEY" "API key for Mistral Small 24B model"
set_secret "MAAS_MISTRAL_SMALL_24B_BASE_URL" "Base URL for Mistral Small 24B endpoint"
set_secret "MAAS_MISTRAL_SMALL_24B_MODEL_NAME" "Model name for Mistral Small 24B"

echo -e "${GREEN}🎉 Secrets setup completed!${NC}"
echo ""
echo -e "${BLUE}📋 Summary:${NC}"
echo "All secrets have been configured for secure deployment."
echo "You can view your secrets at: https://github.com/${REPO}/settings/secrets/actions"
echo ""
echo -e "${YELLOW}⚠️ Remember:${NC}"
echo "- Keep your API keys secure and rotate them regularly"
echo "- Never commit credentials to your repository" 
echo "- Use the .env file for local development (it's gitignored)"
echo ""
echo -e "${BLUE}📖 For more information:${NC}"
echo "- Read the README.md 'Security Setup' section"
echo "- Check GitHub's documentation on repository secrets"
echo ""
echo -e "${GREEN}✅ Your repository is now ready for secure deployment!${NC}"
