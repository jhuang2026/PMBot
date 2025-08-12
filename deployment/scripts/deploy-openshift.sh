#!/bin/bash

# Deploy PM Chatbot to OpenShift
set -e

# Configuration
NAMESPACE=${NAMESPACE:-"pm-chatbot"}
CLUSTER_DOMAIN=${CLUSTER_DOMAIN:-"apps.your-cluster.com"}

echo "🚀 Deploying PM Chatbot to OpenShift..."
echo "Namespace: $NAMESPACE"
echo "Cluster Domain: $CLUSTER_DOMAIN"

# Check if oc is installed
if ! command -v oc &> /dev/null; then
    echo "❌ OpenShift CLI (oc) is not installed"
    echo "Please install it from: https://docs.openshift.com/container-platform/latest/cli_reference/openshift_cli/getting-started-cli.html"
    exit 1
fi

# Check if logged in to OpenShift
if ! oc whoami &> /dev/null; then
    echo "❌ Not logged in to OpenShift"
    echo "Please run: oc login https://your-cluster-api-url:6443"
    exit 1
fi

# Create or switch to namespace
echo "📂 Creating/switching to namespace: $NAMESPACE"
oc new-project $NAMESPACE 2>/dev/null || oc project $NAMESPACE

# Check if we have temporary route files (created by deploy-your-cluster.sh)
if [[ -f "deployment/openshift/route.yaml.tmp" ]]; then
    echo "🔗 Using pre-configured routes with correct hostnames..."
    cp deployment/openshift/route.yaml.tmp deployment/openshift/route.yaml
    
    # Also handle API route if it exists
    if [[ -f "deployment/openshift/route-api.yaml.tmp" ]]; then
        cp deployment/openshift/route-api.yaml.tmp deployment/openshift/route-api.yaml
    fi
else
    echo "🔗 Updating routes with cluster domain..."
    sed -i.bak "s/pm-chatbot.apps.your-cluster.com/pm-chatbot.$CLUSTER_DOMAIN/g" deployment/openshift/route.yaml
    sed -i.bak "s/pm-chatbot-api.apps.your-cluster.com/pm-chatbot-api.$CLUSTER_DOMAIN/g" deployment/openshift/route-api.yaml
fi

# Apply all manifests
echo "📋 Applying OpenShift manifests..."

# Check if secret exists and has real credentials (not placeholders)
SECRET_EXISTS=false
if oc get secret pm-chatbot-secrets -n $NAMESPACE &> /dev/null; then
    CURRENT_JIRA_TOKEN=$(oc get secret pm-chatbot-secrets -n $NAMESPACE -o jsonpath='{.data.JIRA_PERSONAL_TOKEN}' | base64 -d 2>/dev/null || echo "")
    if [[ "$CURRENT_JIRA_TOKEN" != "your_jira_token_here" && -n "$CURRENT_JIRA_TOKEN" ]]; then
        echo "✅ Found existing secret with real credentials - preserving it"
        SECRET_EXISTS=true
    else
        echo "⚠️ Found existing secret with placeholder values - will overwrite"
    fi
fi

if [ "$SECRET_EXISTS" = true ]; then
    # Apply everything except the secret, kustomization, and namespace files
    echo "📝 Applying manifests (excluding secret.yaml, kustomization.yaml, and namespace.yaml)..."
    for file in deployment/openshift/*.yaml; do
        if [[ "$file" != *"secret.yaml" && "$file" != *"kustomization.yaml" && "$file" != *"namespace.yaml" ]]; then
            oc apply -f "$file"
        fi
    done
else
    # Apply everything including the secret
    echo "📝 Applying all manifests..."
    oc apply -k deployment/openshift/
fi

# Wait for deployment to be ready
echo "⏳ Waiting for deployment to be ready..."
oc rollout status deployment/pm-chatbot-deployment -n $NAMESPACE --timeout=600s

# Get the route URL
ROUTE_URL=$(oc get route pm-chatbot-route -n $NAMESPACE -o jsonpath='{.spec.host}')

echo ""
echo "✅ Deployment completed successfully!"
echo ""
echo "🌐 Application URL: https://$ROUTE_URL"
echo ""
echo "📊 Check deployment status:"
echo "  oc get pods -n $NAMESPACE"
echo "  oc logs -f deployment/pm-chatbot-deployment -c streamlit -n $NAMESPACE"
echo ""
echo "🔧 Useful debugging commands:"
echo "  oc describe deployment/pm-chatbot-deployment -n $NAMESPACE"
echo "  oc get events -n $NAMESPACE --sort-by='.lastTimestamp'"
echo "" 