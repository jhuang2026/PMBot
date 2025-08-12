#!/bin/bash

# Helper script to gather information for GitHub secrets setup
set -e

echo "🔐 GitHub Secrets Setup Helper"
echo "=============================="
echo ""
echo "This script will help you gather the information needed to set up"
echo "GitHub secrets for automatic deployment to OpenShift."
echo ""

# Check if logged in to OpenShift
if ! oc whoami &> /dev/null; then
    echo "❌ Not logged in to OpenShift"
    echo ""
    echo "Please log in first:"
    echo "  oc login https://api.cluster-znvdr.znvdr.sandbox203.opentlc.com:6443"
    echo ""
    echo "Then run this script again."
    exit 1
fi

echo "✅ Logged in to OpenShift as: $(oc whoami)"
echo ""

# Get OpenShift information
echo "📋 Gathering OpenShift information..."
echo ""

CURRENT_SERVER=$(oc whoami --show-server)
CURRENT_TOKEN=$(oc whoami -t)
CURRENT_USER=$(oc whoami)

echo "🔗 **OPENSHIFT_SERVER**:"
echo "   Value: $CURRENT_SERVER"
echo ""

echo "🔑 **OPENSHIFT_TOKEN**:"
echo "   Value: $CURRENT_TOKEN"
echo "   ⚠️  Keep this secret! It's your personal access token."
echo ""

# Test OpenShift connection
echo "🧪 Testing OpenShift connection..."
if oc cluster-info &> /dev/null; then
    echo "✅ OpenShift connection working"
else
    echo "⚠️ OpenShift connection test failed"
fi
echo ""

# Quay.io information
echo "📦 Container Registry Information:"
echo ""
echo "🔗 **QUAY_USERNAME**:"
echo "   Your Quay.io username (same as your Red Hat login)"
echo "   Example: rh-ee-jashuang"
echo ""

echo "🔑 **QUAY_PASSWORD**:"
echo "   Option 1: Your Quay.io password"
echo "   Option 2: Robot account token (recommended for CI/CD)"
echo ""
echo "   To create a robot account:"
echo "   1. Go to: https://quay.io/repository/rh-ee-jashuang/pm-chatbot-streamlit?tab=settings"
echo "   2. Click 'Robot Accounts' → 'Create Robot Account'"
echo "   3. Give it write permissions"
echo "   4. Use the generated token as QUAY_PASSWORD"
echo ""

# GitHub repository setup
echo "📂 GitHub Repository Setup:"
echo ""
echo "To add these secrets to your GitHub repository:"
echo ""
echo "1. Go to your repository on GitHub"
echo "2. Click 'Settings' tab"
echo "3. Click 'Secrets and variables' → 'Actions'"
echo "4. Click 'New repository secret'"
echo "5. Add each secret:"
echo ""

cat << 'EOF'
   Secret Name: OPENSHIFT_SERVER
   Secret Value: [Copy the OPENSHIFT_SERVER value from above]

   Secret Name: OPENSHIFT_TOKEN  
   Secret Value: [Copy the OPENSHIFT_TOKEN value from above]

   Secret Name: QUAY_USERNAME
   Secret Value: [Your Quay.io username, e.g., rh-ee-jashuang]

   Secret Name: QUAY_PASSWORD
   Secret Value: [Your Quay.io password or robot token]
EOF

echo ""
echo "🧪 Testing Container Registry Access:"
echo ""

# Check if podman/docker is available for testing
if command -v podman &> /dev/null; then
    echo "To test Quay.io access with podman:"
    echo "  podman login quay.io"
    echo "  podman push quay.io/rh-ee-jashuang/pm-chatbot-streamlit:test"
elif command -v docker &> /dev/null; then
    echo "To test Quay.io access with docker:"
    echo "  docker login quay.io"
    echo "  docker push quay.io/rh-ee-jashuang/pm-chatbot-streamlit:test"
else
    echo "Install podman or docker to test registry access"
fi

echo ""
echo "🚀 After Setting Up Secrets:"
echo ""
echo "1. Commit your changes:"
echo "   git add ."
echo "   git commit -m '🚀 Enable CI/CD pipeline'"
echo "   git push origin main"
echo ""
echo "2. Watch the build at:"
echo "   https://github.com/YOUR_USERNAME/YOUR_REPO/actions"
echo ""
echo "3. The pipeline will:"
echo "   ✅ Build your container in GitHub's cloud (fast!)"
echo "   ✅ Push directly to Quay.io (no slow WiFi upload)"
echo "   ✅ Deploy to your OpenShift cluster automatically"
echo "   ✅ Verify the deployment works"
echo "   ✅ Report the URL where your app is running"
echo ""

# Check current namespace
NAMESPACE=$(oc project -q 2>/dev/null || echo "default")
echo "📍 Current OpenShift namespace: $NAMESPACE"
if [ "$NAMESPACE" != "pm-chatbot" ]; then
    echo "   ⚠️  Consider switching to pm-chatbot namespace:"
    echo "   oc project pm-chatbot"
fi

echo ""
echo "🎯 Summary of what you need to add to GitHub:"
echo ""
printf "%-20s %s\n" "OPENSHIFT_SERVER:" "$CURRENT_SERVER"
printf "%-20s %s\n" "OPENSHIFT_TOKEN:" "[The token shown above]"
printf "%-20s %s\n" "QUAY_USERNAME:" "[Your Quay.io username]"
printf "%-20s %s\n" "QUAY_PASSWORD:" "[Your Quay.io password/token]"

echo ""
echo "🎉 Once set up, every git commit will automatically deploy to your cluster!"
echo "   No more waiting for slow WiFi uploads! 🚀" 