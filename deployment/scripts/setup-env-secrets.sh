#!/bin/bash

# Quick fix: Create OpenShift secret from .env file
set -e

NAMESPACE=${NAMESPACE:-"pm-chatbot"}

echo "🔧 Creating OpenShift secret from .env file..."

# Source the .env file
if [ ! -f ".env" ]; then
    echo "❌ .env file not found"
    exit 1
fi

source .env

echo "✅ Loaded .env file"

# Function to base64 encode
encode_base64() {
    echo -n "$1" | base64
}

# Create the secret
cat > temp-secret-from-env.yaml << EOF
apiVersion: v1
kind: Secret
metadata:
  name: pm-chatbot-secrets
  namespace: $NAMESPACE
  labels:
    app.kubernetes.io/component: application
    app.kubernetes.io/instance: pm-chatbot-instance
    app.kubernetes.io/managed-by: kustomize
    app.kubernetes.io/name: pm-chatbot
    app.kubernetes.io/part-of: pm-chatbot
    app.kubernetes.io/version: 1.0.0
type: Opaque
data:
  # JIRA Configuration
  JIRA_URL: $(encode_base64 "$JIRA_URL")
  JIRA_PERSONAL_TOKEN: $(encode_base64 "$JIRA_PERSONAL_TOKEN")
  
  # MaaS Model: deepseek-r1-qwen-14b
  maas-deepseek-r1-qwen-14b-api-key: $(encode_base64 "$MAAS_DEEPSEEK_R1_QWEN_14B_API_KEY")
  maas-deepseek-r1-qwen-14b-base-url: $(encode_base64 "$MAAS_DEEPSEEK_R1_QWEN_14B_BASE_URL")
  maas-deepseek-r1-qwen-14b-model-name: $(encode_base64 "$MAAS_DEEPSEEK_R1_QWEN_14B_MODEL_NAME")
  
  # MaaS Model: phi-4
  maas-phi-4-api-key: $(encode_base64 "$MAAS_PHI_4_API_KEY")
  maas-phi-4-base-url: $(encode_base64 "$MAAS_PHI_4_BASE_URL")
  maas-phi-4-model-name: $(encode_base64 "$MAAS_PHI_4_MODEL_NAME")
  
  # MaaS Model: granite-3-3-8b-instruct
  maas-granite-3-3-8b-instruct-api-key: $(encode_base64 "$MAAS_GRANITE_3_3_8B_INSTRUCT_API_KEY")
  maas-granite-3-3-8b-instruct-base-url: $(encode_base64 "$MAAS_GRANITE_3_3_8B_INSTRUCT_BASE_URL")
  maas-granite-3-3-8b-instruct-model-name: $(encode_base64 "$MAAS_GRANITE_3_3_8B_INSTRUCT_MODEL_NAME")
  
  # MaaS Model: llama-4-scout-17b
  maas-llama-4-scout-17b-api-key: $(encode_base64 "$MAAS_LLAMA_4_SCOUT_17B_API_KEY")
  maas-llama-4-scout-17b-base-url: $(encode_base64 "$MAAS_LLAMA_4_SCOUT_17B_BASE_URL")
  maas-llama-4-scout-17b-model-name: $(encode_base64 "$MAAS_LLAMA_4_SCOUT_17B_MODEL_NAME")
  
  # MaaS Model: mistral-small-24b
  maas-mistral-small-24b-api-key: $(encode_base64 "$MAAS_MISTRAL_SMALL_24B_API_KEY")
  maas-mistral-small-24b-base-url: $(encode_base64 "$MAAS_MISTRAL_SMALL_24B_BASE_URL")
  maas-mistral-small-24b-model-name: $(encode_base64 "$MAAS_MISTRAL_SMALL_24B_MODEL_NAME")
EOF

echo "📝 Applying secret from .env file..."
oc apply -f temp-secret-from-env.yaml

echo "🧹 Cleaning up temporary file..."
rm temp-secret-from-env.yaml

echo "✅ Secret updated successfully from .env file!"
echo ""
echo "🔄 The pods should now restart automatically and pick up the new secrets."
echo "You can check status with: oc get pods -n $NAMESPACE"