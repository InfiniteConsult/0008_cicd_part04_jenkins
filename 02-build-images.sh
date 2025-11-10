#!/usr/bin/env bash

#
# -----------------------------------------------------------
#               02-build-images.sh
#
#  This is the "build" script. It builds our two custom
#  Docker images:
#
#  1. jenkins-controller: The "Foreman" (UI)
#  2. general-purpose-agent: The "Worker" (Build Tools)
#
#  It's responsible for finding the host's 'docker' GID
#  and passing all the correct build-time arguments to
#  each Dockerfile.
# -----------------------------------------------------------

set -e
echo "🚀 Starting Jenkins Image Build..."

# --- 1. Find Host Docker GID ---
# We need this for the "build-time" GID fix in Dockerfile.controller
HOST_DOCKER_GID=$(getent group docker | cut -d: -f3)

if [ -z "$HOST_DOCKER_GID" ]; then
    echo "⛔ ERROR: 'docker' group not found on host."
    echo "Please ensure the docker group exists and your user is a member."
    exit 1
fi
echo "🔧 Host 'docker' GID found: $HOST_DOCKER_GID"

# --- 2. Define Toolchain Build Arguments ---
# These ARGs must match what Dockerfile.agent expects
PY312="3.12.12"
PY313="3.13.9"
PY314="3.14.0"
GCC15="15.2.0"

# --- 3. Build the Controller Image ---
echo "--- Building 'jenkins-controller:latest' ---"
docker build --progress=plain \
  --build-arg HOST_DOCKER_GID=$HOST_DOCKER_GID \
  -f Dockerfile.controller \
  -t jenkins-controller:latest .
echo "✅ 'jenkins-controller' build complete."


# --- 4. Build the Agent Image ---
echo "--- Building 'general-purpose-agent:latest' ---"
docker build --progress=plain \
  --build-arg py312=$PY312 \
  --build-arg py313=$PY313 \
  --build-arg py314=$PY314 \
  --build-arg gcc15=$GCC15 \
  -f Dockerfile.agent \
  -t general-purpose-agent:latest .
echo "✅ 'general-purpose-agent' build complete."

echo "🎉 Both Jenkins images are built and ready."
echo "   You can now run '03-deploy-controller.sh'."