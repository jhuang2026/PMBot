#!/bin/bash

# Optimized Build and push container images for PM Chatbot with caching
set -e

# Configuration
REGISTRY=${REGISTRY:-"quay.io/rh-ee-jashuang"}
PROJECT_NAME=${PROJECT_NAME:-"pm-chatbot"}

# Detect architecture and set appropriate tags
HOST_ARCH=$(uname -m)
if [[ "$HOST_ARCH" == "arm64" ]]; then
    echo "⚠️ Detected Apple Silicon (ARM64) - building for AMD64 platform for OpenShift compatibility"
    PLATFORM_FLAG="--platform linux/amd64"
    TAG="amd64"
elif [[ "$HOST_ARCH" == "x86_64" ]]; then
    echo "✅ Detected x86_64 - building for AMD64 platform"
    PLATFORM_FLAG="--platform linux/amd64"
    TAG="amd64"
else
    echo "⚠️ Unknown architecture: $HOST_ARCH - defaulting to AMD64"
    PLATFORM_FLAG="--platform linux/amd64"
    TAG="amd64"
fi

echo "🚀 Building PM Chatbot container images with optimization..."
echo "Host Architecture: $HOST_ARCH"
echo "Target Platform: linux/amd64"
echo "Registry: $REGISTRY"
echo "Project: $PROJECT_NAME"
echo "Tag: $TAG"
echo ""

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
    local dockerfile_time=$(stat -f "%m" "$dockerfile" 2>/dev/null || stat -c "%Y" "$dockerfile" 2>/dev/null || echo "0")
    local requirements_time=0
    local source_time=0
    
    # Check relevant files based on component
    if [ "$component" = "streamlit" ]; then
        [ -f "config/requirements.txt" ] && requirements_time=$(stat -f "%m" "config/requirements.txt" 2>/dev/null || stat -c "%Y" "config/requirements.txt" 2>/dev/null || echo "0")
        [ -f "pm_chatbot_main.py" ] && source_time=$(stat -f "%m" "pm_chatbot_main.py" 2>/dev/null || stat -c "%Y" "pm_chatbot_main.py" 2>/dev/null || echo "0")
        # Check other key source files
        for file in vector_database.py document_processor.py rfe_manager.py; do
            if [ -f "$file" ]; then
                local file_time=$(stat -f "%m" "$file" 2>/dev/null || stat -c "%Y" "$file" 2>/dev/null || echo "0")
                [ "$file_time" -gt "$source_time" ] && source_time=$file_time
            fi
        done
    else
        [ -f "config/requirements.api.txt" ] && requirements_time=$(stat -f "%m" "config/requirements.api.txt" 2>/dev/null || stat -c "%Y" "config/requirements.api.txt" 2>/dev/null || echo "0")
        [ -f "api_server.py" ] && source_time=$(stat -f "%m" "api_server.py" 2>/dev/null || stat -c "%Y" "api_server.py" 2>/dev/null || echo "0")
        # Check other key API files
        for file in auth.py atlassian_client.py; do
            if [ -f "$file" ]; then
                local file_time=$(stat -f "%m" "$file" 2>/dev/null || stat -c "%Y" "$file" 2>/dev/null || echo "0")
                [ "$file_time" -gt "$source_time" ] && source_time=$file_time
            fi
        done
    fi
    
    # Convert image creation time to epoch (try multiple formats)
    local image_epoch=0
    if command -v gdate >/dev/null 2>&1; then
        # Use GNU date if available (brew install coreutils on macOS)
        image_epoch=$(gdate -d "$local_created" "+%s" 2>/dev/null || echo "0")
    else
        # Try different date parsing approaches
        image_epoch=$(date -j -f "%Y-%m-%dT%H:%M:%S" "$(echo $local_created | cut -d'.' -f1)" "+%s" 2>/dev/null || echo "0")
    fi
    
    # If we can't parse the date, assume rebuild is needed
    if [ "$image_epoch" = "0" ]; then
        echo "📦 $component: Cannot parse image date, rebuild needed"
        return 0
    fi
    
    # If any source file is newer than image, rebuild
    if [ "$dockerfile_time" -gt "$image_epoch" ] || [ "$requirements_time" -gt "$image_epoch" ] || [ "$source_time" -gt "$image_epoch" ]; then
        echo "📦 $component: Source files newer than image, rebuild needed"
        echo "   Dockerfile: $(date -r $dockerfile_time 2>/dev/null || echo 'unknown')"
        echo "   Requirements: $(date -r $requirements_time 2>/dev/null || echo 'unknown')"
        echo "   Source: $(date -r $source_time 2>/dev/null || echo 'unknown')"
        echo "   Image: $(echo $local_created | cut -d'.' -f1)"
        return 0
    fi
    
    echo "✅ $component: Image up-to-date, skipping rebuild"
    return 1
}

# Function to build image with caching
build_image_cached() {
    local component=$1
    local dockerfile=$2
    local image_tag="$REGISTRY/$PROJECT_NAME-$component:$TAG"
    local latest_tag="$REGISTRY/$PROJECT_NAME-$component:latest"
    
    echo "📦 Building $component image with layer caching..."
    
    # Podman automatically uses layer caching, so we just need to build efficiently
    # The --layers flag enables layer caching for intermediate layers
    podman build $PLATFORM_FLAG \
        -f "$dockerfile" \
        -t "$image_tag" \
        -t "$latest_tag" \
        --layers \
        .
    
    echo "✅ $component image built successfully"
}

# Function to push images
push_images() {
    local component=$1
    local image_tag="$REGISTRY/$PROJECT_NAME-$component:$TAG"
    local latest_tag="$REGISTRY/$PROJECT_NAME-$component:latest"
    
    echo "📤 Pushing $component images to registry..."
    
    # Push in parallel using background jobs
    podman push "$image_tag" &
    push_pid1=$!
    podman push "$latest_tag" &
    push_pid2=$!
    
    # Wait for both pushes to complete
    wait $push_pid1 && echo "✅ Pushed $image_tag"
    wait $push_pid2 && echo "✅ Pushed $latest_tag"
}

# Clean up any existing dangling images to avoid conflicts
echo "🧹 Cleaning up dangling images..."
podman image prune -f --filter "dangling=true" || true

# Check if Streamlit rebuild is needed
STREAMLIT_REBUILD=false
if needs_rebuild "streamlit" "deployment/docker/Dockerfile.streamlit"; then
    STREAMLIT_REBUILD=true
fi

# Check if API rebuild is needed
API_REBUILD=false
if needs_rebuild "api" "deployment/docker/Dockerfile.api"; then
    API_REBUILD=true
fi

# If no rebuilds needed, we're done
if [ "$STREAMLIT_REBUILD" = "false" ] && [ "$API_REBUILD" = "false" ]; then
    echo "🎉 All images are up-to-date! No rebuilds needed."
    echo ""
    echo "📋 Current images:"
    podman images | grep "$REGISTRY/$PROJECT_NAME" || echo "No images found"
    exit 0
fi

# Build images in parallel if both need rebuilding
if [ "$STREAMLIT_REBUILD" = "true" ] && [ "$API_REBUILD" = "true" ]; then
    echo "🔄 Building both images in parallel..."
    
    # Build Streamlit in background
    (
        build_image_cached "streamlit" "deployment/docker/Dockerfile.streamlit"
    ) &
    streamlit_build_pid=$!
    
    # Build API in background
    (
        build_image_cached "api" "deployment/docker/Dockerfile.api"
    ) &
    api_build_pid=$!
    
    # Wait for both builds to complete
    echo "⏳ Waiting for parallel builds to complete..."
    wait $streamlit_build_pid && echo "✅ Streamlit build completed"
    wait $api_build_pid && echo "✅ API build completed"
    
elif [ "$STREAMLIT_REBUILD" = "true" ]; then
    build_image_cached "streamlit" "deployment/docker/Dockerfile.streamlit"
elif [ "$API_REBUILD" = "true" ]; then
    build_image_cached "api" "deployment/docker/Dockerfile.api"
fi

# Push all images (both rebuilt and existing)
echo "📤 Pushing images to registry..."

# Always push both sets of images (in case tags were updated)
if [ "$STREAMLIT_REBUILD" = "true" ] || [ "$API_REBUILD" = "true" ]; then
    # Push rebuilt images in parallel
    push_images "streamlit" &
    streamlit_push_pid=$!
    push_images "api" &
    api_push_pid=$!
    
    # Wait for both pushes
    echo "⏳ Waiting for parallel pushes to complete..."
    wait $streamlit_push_pid && echo "✅ Streamlit push completed"
    wait $api_push_pid && echo "✅ API push completed"
else
    echo "ℹ️ No new images to push"
fi

echo ""
echo "✅ Optimized build completed!"
echo ""
echo "📋 Images available:"
echo "  - Streamlit: $REGISTRY/$PROJECT_NAME-streamlit:$TAG"
echo "  - Streamlit: $REGISTRY/$PROJECT_NAME-streamlit:latest"
echo "  - API: $REGISTRY/$PROJECT_NAME-api:$TAG"
echo "  - API: $REGISTRY/$PROJECT_NAME-api:latest"
echo ""
echo "🔍 Verify images in registry:"
echo "  - https://quay.io/repository/rh-ee-jashuang/pm-chatbot-streamlit"
echo "  - https://quay.io/repository/rh-ee-jashuang/pm-chatbot-api"
echo ""

# Display build time savings
if [ "$STREAMLIT_REBUILD" = "false" ] || [ "$API_REBUILD" = "false" ]; then
    echo "💡 Build optimization saved time by skipping unnecessary rebuilds!"
fi