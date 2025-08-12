#!/bin/bash

# Script to copy pre-built vector database to OpenShift deployment
# This copies the local vector_db and document_cache to the running pod

set -e

NAMESPACE="pm-chatbot"
APP_LABEL="app=pm-chatbot"

echo "🚀 Copying pre-built vector database to OpenShift deployment..."

# Get the running pod name
POD_NAME=$(oc get pods -n "$NAMESPACE" -l "$APP_LABEL" -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || echo "")

if [ -z "$POD_NAME" ]; then
    echo "❌ No running pod found with label $APP_LABEL in namespace $NAMESPACE"
    echo "💡 Make sure the deployment is running: oc get pods -n $NAMESPACE"
    exit 1
fi

echo "📦 Found pod: $POD_NAME"

# Check if local vector database exists
if [ ! -d "./vector_db" ]; then
    echo "❌ Local vector_db directory not found in current directory"
    echo "💡 Please run this script from the project root directory"
    exit 1
fi

if [ ! -f "./vector_db/metadata.json" ]; then
    echo "❌ Vector database metadata.json not found"
    echo "💡 Please ensure your local vector database is built"
    exit 1
fi

# Display vector database stats
echo "📊 Local vector database stats:"
cat "./vector_db/metadata.json" | grep -E '"total_documents"|"total_chunks"' || echo "Unable to read stats"

# Copy vector database files
echo "📋 Copying vector database files..."
oc exec -n "$NAMESPACE" "$POD_NAME" -- mkdir -p /app/vector_db
oc rsync "./vector_db/" "$NAMESPACE/$POD_NAME:/app/vector_db/" --no-perms=true --delete=false

# Copy document cache
if [ -d "./document_cache" ]; then
    echo "📋 Copying document cache..."
    oc exec -n "$NAMESPACE" "$POD_NAME" -- mkdir -p /app/document_cache
    oc rsync "./document_cache/" "$NAMESPACE/$POD_NAME:/app/document_cache/" --no-perms=true --delete=false
fi

# Copy documents directory
if [ -d "./documents" ]; then
    echo "📋 Copying documents directory..."
    oc exec -n "$NAMESPACE" "$POD_NAME" -- mkdir -p /app/documents
    oc rsync "./documents/" "$NAMESPACE/$POD_NAME:/app/documents/" --no-perms=true --delete=false
fi

# Verify the copy was successful
echo "🔍 Verifying vector database in pod..."
oc exec -n "$NAMESPACE" "$POD_NAME" -- ls -la /app/vector_db/ || echo "Warning: Could not list vector_db contents"

# Check if metadata.json exists in the pod
oc exec -n "$NAMESPACE" "$POD_NAME" -- cat /app/vector_db/metadata.json 2>/dev/null && echo "✅ Vector database copied successfully!" || echo "❌ Vector database copy may have failed"

# Restart the pod to reinitialize with the new data
echo "🔄 Restarting deployment to load new vector database..."
oc rollout restart deployment/pm-chatbot-deployment -n "$NAMESPACE"
oc rollout status deployment/pm-chatbot-deployment -n "$NAMESPACE" --timeout=300s

echo "✅ Vector database deployment complete!"
echo "🌐 Check your application - it should now show the correct number of documents and chunks"
echo ""
echo "🔗 To access your application:"
echo "   oc get routes -n $NAMESPACE"