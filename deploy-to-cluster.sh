#!/bin/bash

# 🚀 PM Chatbot Deployment Script
# ===============================
# This script handles deployment to BOTH new and existing OpenShift clusters
# 
# Usage Examples:
#   ./deploy-to-cluster.sh                                      # Use defaults (current cluster)
#   ./deploy-to-cluster.sh -a https://api.your-cluster:6443     # Specify different cluster
#   ./deploy-to-cluster.sh --help                               # Show all options
#
# What this script does:
#   ✅ Handles both NEW and EXISTING clusters
#   ✅ Creates namespace if needed
#   ✅ Fixes registry/Podman issues automatically  
#   ✅ Builds and pushes images
#   ✅ Sets up secrets
#   ✅ Deploys application
#   ✅ Uploads RAG cache for faster startup

set -e

# Function to show usage
show_usage() {
    echo "🚀 PM Chatbot Deployment Script"
    echo "==============================="
    echo ""
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Deploy PM Chatbot to your OpenShift cluster (works with both new and existing clusters)"
    echo ""
    echo "Options:"
    echo "  -a, --api URL          Cluster API URL"
    echo "  -d, --domain DOMAIN    Apps domain (optional, will be inferred from API if not provided)"
    echo "  -r, --registry REG     Container registry (default: quay.io/rh-ee-jashuang)"
    echo "  -n, --namespace NS     Namespace (default: pm-chatbot)"
    echo "  -h, --help            Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                                                           # Use current defaults"
    echo "  $0 -a https://api.cluster-abc.sandbox.com:6443              # Deploy to different cluster"
    echo "  $0 --api https://api.new-cluster.com:6443 --namespace myapp  # Custom namespace"
    echo ""
    echo "💡 This script automatically:"
    echo "   • Detects if cluster is new or existing"
    echo "   • Creates namespace if needed"
    echo "   • Handles Podman/registry issues"
    echo "   • Sets up all required resources"
    echo "   • Uploads RAG cache for faster startup"
    echo ""
}

# Config file to remember last deployment settings
CONFIG_FILE=".deploy-config"

# Function to load saved configuration
load_config() {
    if [ -f "$CONFIG_FILE" ]; then
        source "$CONFIG_FILE"
        echo "📋 Loaded previous deployment configuration"
        echo "   Last cluster: $SAVED_CLUSTER_API"
        echo "   Last registry: $SAVED_REGISTRY"
        echo "   Last namespace: $SAVED_NAMESPACE"
        echo ""
    fi
}

# Function to save current configuration
save_config() {
    cat > "$CONFIG_FILE" << EOF
# Last deployment configuration (auto-generated)
SAVED_CLUSTER_API="$CLUSTER_API"
SAVED_CLUSTER_DOMAIN="$CLUSTER_DOMAIN"
SAVED_NAMESPACE="$NAMESPACE"
SAVED_PROJECT_NAME="$PROJECT_NAME"
SAVED_REGISTRY="$REGISTRY"
EOF
    echo "💾 Saved deployment configuration for next time"
}

# Load previous configuration
load_config

# Default values (fallback if no saved config)
DEFAULT_CLUSTER_API="${SAVED_CLUSTER_API:-https://api.cluster-znvdr.znvdr.sandbox203.opentlc.com:6443}"
DEFAULT_CLUSTER_DOMAIN="${SAVED_CLUSTER_DOMAIN:-apps.cluster-znvdr.znvdr.sandbox203.opentlc.com}"
DEFAULT_NAMESPACE="${SAVED_NAMESPACE:-pm-chatbot}"
DEFAULT_PROJECT_NAME="${SAVED_PROJECT_NAME:-pm-chatbot}"
DEFAULT_REGISTRY="${SAVED_REGISTRY:-quay.io/rh-ee-jashuang}"

# Initialize variables with defaults (using saved values if available)
CLUSTER_API="$DEFAULT_CLUSTER_API"
CLUSTER_DOMAIN=""
NAMESPACE="$DEFAULT_NAMESPACE"
PROJECT_NAME="$DEFAULT_PROJECT_NAME"
REGISTRY="$DEFAULT_REGISTRY"

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -a|--api)
            CLUSTER_API="$2"
            shift 2
            ;;
        -d|--domain)
            CLUSTER_DOMAIN="$2"
            shift 2
            ;;
        -r|--registry)
            REGISTRY="$2"
            shift 2
            ;;
        -n|--namespace)
            NAMESPACE="$2"
            PROJECT_NAME="$2"
            shift 2
            ;;
        -h|--help)
            show_usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# If domain not provided, infer it from API URL
if [[ -z "$CLUSTER_DOMAIN" ]]; then
    # Extract cluster identifier from API URL
    # Example: https://api.cluster-8269x.8269x.sandbox2049.opentlc.com:6443 -> apps.cluster-8269x.8269x.sandbox2049.opentlc.com
    if [[ "$CLUSTER_API" =~ https://api\.(.+):6443 ]]; then
        CLUSTER_DOMAIN="apps.${BASH_REMATCH[1]}"
    else
        echo "❌ Unable to infer cluster domain from API URL: $CLUSTER_API"
        echo "Please provide the domain explicitly with --domain option"
        exit 1
    fi
fi

# Export for use by other scripts
export CLUSTER_API
export CLUSTER_DOMAIN
export NAMESPACE
export PROJECT_NAME
export REGISTRY

echo "🚀 Deploying PM Chatbot to your OpenShift cluster..."
echo ""
echo "🔧 Configuration:"
echo "  Cluster API: $CLUSTER_API"
echo "  Apps Domain: $CLUSTER_DOMAIN"
echo "  Registry: $REGISTRY"
echo "  Namespace: $NAMESPACE"
echo ""

# Function to wait for deployment to be ready
wait_for_deployment() {
    local deployment_name=$1
    local namespace=$2
    local timeout=${3:-300}
    
    echo "⏳ Waiting for deployment $deployment_name to be ready..."
    if ! oc rollout status deployment/$deployment_name -n $namespace --timeout=${timeout}s; then
        echo "❌ Deployment $deployment_name failed to become ready within ${timeout} seconds"
        echo "📋 Pod status:"
        oc get pods -n $namespace -l app=pm-chatbot
        echo "📋 Recent events:"
        oc get events -n $namespace --sort-by='.lastTimestamp' | tail -10
        return 1
    fi
    echo "✅ Deployment $deployment_name is ready"
}

# Step 1: Login to OpenShift
echo "🔐 Step 1: Login to OpenShift"
if ! oc whoami &> /dev/null; then
    echo "Please login to OpenShift:"
    oc login $CLUSTER_API
else
    echo "✅ Already logged in as: $(oc whoami)"
    echo "Current server: $(oc whoami --show-server)"
    
    # Check if we're connected to the right cluster
    CURRENT_SERVER=$(oc whoami --show-server)
    if [[ "$CURRENT_SERVER" != "$CLUSTER_API" ]]; then
        echo "⚠️ Currently connected to different cluster: $CURRENT_SERVER"
        echo "Logging into the target cluster: $CLUSTER_API"
        oc login $CLUSTER_API
    fi
fi

# Step 1.5: Ensure namespace exists
echo "📂 Step 1.5: Ensuring namespace exists..."
if oc get namespace $NAMESPACE &> /dev/null; then
    echo "✅ Namespace '$NAMESPACE' already exists"
    oc project $NAMESPACE
else
    echo "📝 Creating namespace '$NAMESPACE'..."
    oc new-project $NAMESPACE
    echo "✅ Namespace '$NAMESPACE' created and set as current project"
fi

# Step 2: Login to Quay (if needed)
echo "🔐 Step 1.5: Podman and Quay setup"

# Function to start Podman on macOS
start_podman_macos() {
    echo "🍎 Detected macOS - attempting to start Podman machine..."
    
    # Check if podman machine exists
    if ! podman machine list 2>/dev/null | grep -q "podman-machine-default"; then
        echo "📝 Initializing Podman machine (first time setup)..."
        if ! podman machine init; then
            echo "❌ Failed to initialize Podman machine"
            return 1
        fi
    fi
    
    # Start the machine if it's not running
    if ! podman machine list 2>/dev/null | grep -q "Currently running"; then
        echo "▶️ Starting Podman machine..."
        if ! podman machine start; then
            echo "❌ Failed to start Podman machine"
            return 1
        fi
        echo "✅ Podman machine started successfully"
        # Wait a moment for the machine to be fully ready
        sleep 3
    else
        echo "✅ Podman machine is already running"
    fi
    
    return 0
}

# Function to check and start Podman on Linux
start_podman_linux() {
    echo "🐧 Detected Linux - checking Podman service..."
    
    # Check if systemd service exists and try to start it
    if systemctl --user list-unit-files podman.socket &>/dev/null; then
        echo "📝 Starting Podman user service..."
        systemctl --user start podman.socket || true
    fi
    
    # On Linux, Podman should work without additional setup
    echo "✅ Podman should be ready on Linux"
    return 0
}

# Check if Podman is available
if ! podman info &> /dev/null; then
    echo "⚠️ Podman is not available or not working!"
    echo "🔧 Attempting to start Podman automatically..."
    
    # Detect OS and try appropriate startup method
    case "$(uname -s)" in
        Darwin*)
            if start_podman_macos; then
                echo "✅ Podman started successfully on macOS"
            else
                echo "❌ Failed to start Podman automatically on macOS"
                echo "📋 Please run manually:"
                echo "   brew install podman (if not installed)"
                echo "   podman machine init && podman machine start"
                exit 1
            fi
            ;;
        Linux*)
            if start_podman_linux; then
                echo "✅ Podman setup completed on Linux"
            else
                echo "❌ Podman setup failed on Linux"
                echo "📋 Please ensure Podman is installed and working"
                exit 1
            fi
            ;;
        *)
            echo "❌ Unsupported operating system: $(uname -s)"
            echo "📋 Please ensure Podman is installed and running manually"
            exit 1
            ;;
    esac
    
    # Verify Podman is now working
    echo "🔍 Verifying Podman is now working..."
    sleep 2
    if ! podman info &> /dev/null; then
        echo "❌ Podman is still not working after startup attempt"
        echo "📋 Please check Podman installation and try again"
        exit 1
    fi
fi

echo "✅ Podman is available and working"

echo "If prompted, login to Quay with your Red Hat credentials:"
podman login quay.io

# Step 3: Handle existing deployment (cleanup for redeployment)
echo "🧹 Step 2: Checking for existing deployment..."
if oc get deployment pm-chatbot-deployment -n $NAMESPACE &> /dev/null; then
    echo "⚠️ Found existing deployment. Cleaning up for redeployment..."
    
    # Delete deployment to avoid volume conflicts
    echo "Deleting existing deployment..."
    oc delete deployment pm-chatbot-deployment -n $NAMESPACE --wait=true || true
    
    # Wait for pods to be fully terminated
    echo "⏳ Waiting for pods to terminate..."
    sleep 10
    
    # Check if any pods are still running
    if oc get pods -n $NAMESPACE --no-headers 2>/dev/null | grep -q "pm-chatbot"; then
        echo "⏳ Waiting for remaining pods to terminate..."
        oc wait --for=delete pods -l app=pm-chatbot -n $NAMESPACE --timeout=60s || true
    fi
    
    echo "✅ Cleanup completed"
else
    echo "ℹ️ No existing deployment found"
fi

# Step 4: Smart image building (with change detection and caching)
echo "🏗️ Step 3: Smart image building and pushing..."

# Function to check if images need rebuilding
needs_rebuild() {
    local component=$1
    local dockerfile=$2
    local image_tag="$REGISTRY/$PROJECT_NAME-$component:latest"
    
    # Check if image exists locally first
    if ! podman image exists "$image_tag" 2>/dev/null; then
        echo "📦 $component: Image not found locally, rebuild needed"
        return 0
    fi
    
    # Get local image creation time
    local local_created=$(podman image inspect "$image_tag" --format '{{.Created}}' 2>/dev/null || echo "")
    if [ -z "$local_created" ]; then
        echo "📦 $component: Cannot determine local image age, rebuild needed"
        return 0
    fi
    
    # Check if any source files are newer than the image
    local dockerfile_time=$(stat -f "%m" "$dockerfile" 2>/dev/null || echo "0")
    local requirements_time=0
    local source_time=0
    
    # Check relevant files based on component
    if [ "$component" = "streamlit" ]; then
        [ -f "config/requirements.txt" ] && requirements_time=$(stat -f "%m" "config/requirements.txt")
        [ -f "pm_chatbot_main.py" ] && source_time=$(stat -f "%m" "pm_chatbot_main.py")
    else
        [ -f "config/requirements.api.txt" ] && requirements_time=$(stat -f "%m" "config/requirements.api.txt")
        [ -f "api_server.py" ] && source_time=$(stat -f "%m" "api_server.py")
    fi
    
    # Convert image creation time to epoch (simplified check)
    local image_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$(echo $local_created | cut -d'.' -f1)" "+%s" 2>/dev/null || echo "0")
    
    # If any source file is newer than image, rebuild
    if [ "$dockerfile_time" -gt "$image_epoch" ] || [ "$requirements_time" -gt "$image_epoch" ] || [ "$source_time" -gt "$image_epoch" ]; then
        echo "📦 $component: Source files newer than image, rebuild needed"
        return 0
    fi
    
    echo "✅ $component: Image up-to-date, skipping rebuild"
    return 1
}

# Optimized build script with caching
./deployment/scripts/build-images-optimized.sh

# Step 5: Set up secrets
echo "🔐 Step 4: Setting up secrets from .env file..."
if [ ! -f ".env" ]; then
    echo "❌ Error: .env file not found!"
    echo "Please create a .env file with your credentials (see env.template)"
    exit 1
fi
echo "✅ Found .env file - creating secrets automatically..."
./deployment/scripts/setup-env-secrets.sh

# Step 6: Deploy (with smart configuration caching)
echo "🚀 Step 5: Deploying to OpenShift..."

# Cache file for deployment state
DEPLOY_CACHE_FILE=".deploy-cache"

# Function to check if OpenShift configs need updating
needs_config_update() {
    # Check if cache file exists
    if [ ! -f "$DEPLOY_CACHE_FILE" ]; then
        echo "📦 No deployment cache found, full deployment needed"
        return 0
    fi
    
    # Load cached values
    source "$DEPLOY_CACHE_FILE"
    
    # Check if deployments actually exist in the cluster
    if ! oc get deployment pm-chatbot-deployment -n $NAMESPACE &> /dev/null; then
        echo "📦 Streamlit deployment missing, full deployment needed"
        return 0
    fi
    
    if ! oc get deployment pm-chatbot-api -n $NAMESPACE &> /dev/null; then
        echo "📦 API deployment missing, full deployment needed"
        return 0
    fi
    
    # Check if cluster or key parameters changed
    if [ "$CACHED_CLUSTER_DOMAIN" != "$CLUSTER_DOMAIN" ] || \
       [ "$CACHED_NAMESPACE" != "$NAMESPACE" ] || \
       [ "$CACHED_REGISTRY" != "$REGISTRY" ]; then
        echo "📦 Cluster/config changed, deployment update needed"
        return 0
    fi
    
    # Check if OpenShift config files are newer than last deployment
    local last_deploy_time=${CACHED_DEPLOY_TIME:-0}
    for config_file in deployment/openshift/*.yaml; do
        if [ -f "$config_file" ]; then
            local file_time=$(stat -f "%m" "$config_file" 2>/dev/null || stat -c "%Y" "$config_file" 2>/dev/null || echo "0")
            if [ "$file_time" -gt "$last_deploy_time" ]; then
                echo "📦 OpenShift config files updated, deployment needed"
                return 0
            fi
        fi
    done
    
    echo "✅ OpenShift configuration up-to-date, skipping unnecessary updates"
    return 1
}

# Function to save deployment cache
save_deploy_cache() {
    cat > "$DEPLOY_CACHE_FILE" << EOF
# Deployment cache (auto-generated)
CACHED_CLUSTER_DOMAIN="$CLUSTER_DOMAIN"
CACHED_NAMESPACE="$NAMESPACE"
CACHED_REGISTRY="$REGISTRY"
CACHED_DEPLOY_TIME="$(date +%s)"
EOF
}

# Check if we need to update configurations
NEEDS_DEPLOY_UPDATE=true
if ! needs_config_update; then
    NEEDS_DEPLOY_UPDATE=false
    echo "⚡ Skipping configuration update - using cached deployment state"
fi

if [ "$NEEDS_DEPLOY_UPDATE" = "true" ]; then
    # Update routes with correct hostname before deploying
    echo "🌐 Setting up routes for cluster domain: $CLUSTER_DOMAIN"
    ROUTE_HOSTNAME="pm-chatbot.$CLUSTER_DOMAIN"
    API_ROUTE_HOSTNAME="pm-chatbot-api.$CLUSTER_DOMAIN"

    # Create temporary route files with correct hostnames
    cp deployment/openshift/route.yaml deployment/openshift/route.yaml.tmp
    cp deployment/openshift/route-api.yaml deployment/openshift/route-api.yaml.tmp

# Main app route
cat > deployment/openshift/route.yaml.tmp << EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: pm-chatbot-route
  namespace: pm-chatbot
  labels:
    app: pm-chatbot
spec:
  host: $ROUTE_HOSTNAME
  to:
    kind: Service
    name: streamlit-service
    weight: 100
  port:
    targetPort: streamlit
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  wildcardPolicy: None
EOF

# API route
cat > deployment/openshift/route-api.yaml.tmp << EOF
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: pm-chatbot-api-route
  namespace: pm-chatbot
  labels:
    app: pm-chatbot
    component: api
spec:
  host: $API_ROUTE_HOSTNAME
  to:
    kind: Service
    name: pm-chatbot-api-service
    weight: 100
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
  wildcardPolicy: None
EOF

    # Deploy with updated routes
    echo "🚀 Applying OpenShift configurations..."
    ./deployment/scripts/deploy-openshift.sh
    
    # Clean up temporary files
    rm -f deployment/openshift/route.yaml.tmp deployment/openshift/route-api.yaml.tmp
    
    # Save deployment cache
    save_deploy_cache
    
    echo "✅ OpenShift configuration applied and cached"
else
    echo "⚡ Using cached OpenShift configuration - skipping deploy step"
fi

# Step 7: Wait for deployment to be ready (with parallel readiness check)
echo "⏳ Step 6: Waiting for deployments to be ready..."

# Function to wait for specific deployment
wait_for_specific_deployment() {
    local deployment=$1
    local desc=$2
    echo "⏳ Waiting for $desc deployment ($deployment)..."
    if wait_for_deployment "$deployment" "$NAMESPACE" 600; then
        echo "✅ $desc deployment ready"
        return 0
    else
        echo "❌ $desc deployment failed"
        return 1
    fi
}

# Wait for both deployments in parallel
wait_for_specific_deployment "pm-chatbot-deployment" "Streamlit" &
STREAMLIT_WAIT_PID=$!

# Check if API deployment exists before waiting
if oc get deployment pm-chatbot-api -n $NAMESPACE &> /dev/null; then
    wait_for_specific_deployment "pm-chatbot-api" "API" &
    API_WAIT_PID=$!
else
    echo "ℹ️ API deployment not found, skipping API wait"
    API_WAIT_PID=""
fi

# Wait for Streamlit deployment
echo "⏳ Waiting for Streamlit deployment..."
if ! wait $STREAMLIT_WAIT_PID; then
    echo "❌ Streamlit deployment failed"
    exit 1
fi

# Wait for API deployment if it exists
if [ -n "$API_WAIT_PID" ]; then
    echo "⏳ Waiting for API deployment..."
    if ! wait $API_WAIT_PID; then
        echo "❌ API deployment failed"
        exit 1
    fi
fi

echo "✅ All deployments are ready!"

# Step 8: Smart RAG Cache Upload (Performance Optimization)
echo "📦 Step 7: Smart RAG cache upload..."

# Function to check if cache upload is needed
needs_cache_upload() {
    # Check if cache files exist locally
    if [ ! -d "./document_cache" ] || [ ! "$(ls -A ./document_cache 2>/dev/null)" ]; then
        echo "ℹ️ No local document cache found"
        return 1
    fi
    
    # Get the running Streamlit pod
    local streamlit_pod=$(oc get pods -n $NAMESPACE -l "app=pm-chatbot" -l "app.kubernetes.io/component=application" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -z "$streamlit_pod" ]; then
        echo "⚠️ No Streamlit pod found for cache check"
        return 0  # Upload needed if we can't check
    fi
    
    # Check if cache already exists in pod
    if oc exec $streamlit_pod -n $NAMESPACE -- test -f /app/vector_db/metadata.json 2>/dev/null; then
        local remote_cache_time=$(oc exec $streamlit_pod -n $NAMESPACE -- stat -c "%Y" /app/vector_db/metadata.json 2>/dev/null || echo "0")
        local local_cache_time=0
        
        # Find newest local cache file
        for cache_file in ./document_cache/* ./vector_db/*; do
            if [ -f "$cache_file" ]; then
                local file_time=$(stat -f "%m" "$cache_file" 2>/dev/null || stat -c "%Y" "$cache_file" 2>/dev/null || echo "0")
                [ "$file_time" -gt "$local_cache_time" ] && local_cache_time=$file_time
            fi
        done
        
        if [ "$local_cache_time" -le "$remote_cache_time" ]; then
            echo "✅ Remote cache is up-to-date, skipping upload"
            return 1
        fi
    fi
    
    echo "📦 Cache upload needed"
    return 0
}

# Check if cache upload is needed
if needs_cache_upload; then
    echo "📋 Uploading RAG cache for faster startup..."
    
    # Wait for Streamlit pod to be ready
    echo "⏳ Waiting for Streamlit pod to be ready..."
    oc wait --for=condition=ready pod -l app=pm-chatbot -l app.kubernetes.io/component=application -n $NAMESPACE --timeout=300s
    
    # Get the running Streamlit pod
    STREAMLIT_POD=$(oc get pods -n $NAMESPACE -l "app=pm-chatbot" -l "app.kubernetes.io/component=application" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null)
    
    if [ -n "$STREAMLIT_POD" ]; then
        echo "📦 Uploading to pod: $STREAMLIT_POD"
        
        # Upload document cache
        echo "📋 Uploading document cache..."
        oc cp ./document_cache/. $NAMESPACE/$STREAMLIT_POD:/app/document_cache/
        echo "✅ Document cache uploaded successfully"
        
        # Also upload vector database if it exists
        if [ -d "./vector_db" ] && [ -f "./vector_db/metadata.json" ]; then
            echo "📊 Uploading vector database..."
            oc cp ./vector_db/. $NAMESPACE/$STREAMLIT_POD:/app/vector_db/
            echo "✅ Vector database uploaded successfully"
            
            # Display uploaded cache stats
            echo "📊 Uploaded cache stats:"
            oc exec $STREAMLIT_POD -n $NAMESPACE -- cat /app/vector_db/metadata.json 2>/dev/null | grep -E '"total_documents"|"total_chunks"' || echo "Stats not available"
            
            # Restart pod to load the cache
            echo "🔄 Restarting Streamlit to load uploaded cache..."
            oc delete pod $STREAMLIT_POD -n $NAMESPACE
            
            # Wait for new pod to be ready
            echo "⏳ Waiting for restarted pod to be ready..."
            oc wait --for=condition=ready pod -l app=pm-chatbot -l app.kubernetes.io/component=application -n $NAMESPACE --timeout=300s
            echo "✅ RAG cache upload completed!"
        else
            echo "ℹ️ Vector database not found - will be built automatically on first use"
        fi
    else
        echo "⚠️ Could not find Streamlit pod for cache upload"
        echo "📋 Pod status:"
        oc get pods -n $NAMESPACE
    fi
else
    echo "ℹ️ No document cache found - will be built automatically on first use"
fi

# Step 9: Verify services have endpoints
echo "🔍 Step 8: Verifying services..."
echo "Checking service endpoints..."
for i in {1..30}; do
    if oc get endpoints streamlit-service -n $NAMESPACE -o jsonpath='{.subsets[*].addresses[*].ip}' | grep -q .; then
        echo "✅ Streamlit service has endpoints"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "❌ Streamlit service has no endpoints after 30 attempts"
        echo "📋 Service status:"
        oc describe service streamlit-service -n $NAMESPACE
        echo "📋 Endpoints:"
        oc get endpoints -n $NAMESPACE
        exit 1
    fi
    echo "⏳ Waiting for service endpoints... (attempt $i/30)"
    sleep 10
done

# Step 10: Final verification
echo "🔍 Step 9: Final verification..."
echo "📋 Pod status:"
oc get pods -n $NAMESPACE

echo "📋 Service status:"
oc get services -n $NAMESPACE

echo "📋 Route status:"
oc get routes -n $NAMESPACE -o custom-columns=NAME:.metadata.name,URL:.spec.host,TLS:.spec.tls.termination

# Save configuration for next deployment
save_config

# Final status
echo ""
echo "🎉 Deployment completed successfully!"
echo ""
echo "🌐 Your applications are available at:"
echo "   📱 Main App (Streamlit): https://$ROUTE_HOSTNAME"
echo "   🔌 API Server (MCP):     https://$API_ROUTE_HOSTNAME"
echo ""
echo "🔍 API Documentation:"
echo "   📖 Swagger UI: https://$API_ROUTE_HOSTNAME/docs"
echo "   🤖 MCP Endpoint: https://$API_ROUTE_HOSTNAME/mcp"
echo ""
echo "🔍 Useful commands for monitoring:"
echo "   oc get pods -n $NAMESPACE"
echo "   oc logs -f deployment/pm-chatbot-deployment -c streamlit -n $NAMESPACE"
echo "   oc logs -f deployment/pm-chatbot-api -c api -n $NAMESPACE"
echo ""
echo "⚡ Performance Optimizations Summary:"
echo "   🏗️ Smart image building - only rebuilds when source changes"
echo "   📦 Docker layer caching - reuses unchanged layers"
echo "   🚀 Parallel operations - builds and deploys concurrently"
echo "   💾 Configuration caching - skips unnecessary config updates"
echo "   📋 Smart cache upload - only uploads when cache is newer"
echo ""
echo "💡 Next deployment to this cluster can use: ./deploy-to-cluster.sh"
echo "   (will be even faster thanks to caching!)"
echo ""