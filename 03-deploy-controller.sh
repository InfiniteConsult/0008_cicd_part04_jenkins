#!/usr/bin/env bash

#
# -----------------------------------------------------------
#               03-deploy-controller.sh
#
#  This is the "deploy" script. It runs the 'docker run'
#  command to launch our 'jenkins-controller' container.
#
#  It's responsible for connecting all our "first principles"
#  components together:
#
#  1. Network:    Connects to 'cicd-net' with hostname 'jenkins'.
#  2. Ports:      Publishes the UI (10400) and Agent (10401) ports.
#  3. Secrets:    Passes the *scoped* 'jenkins.env' file.
#  4. Volumes:    Mounts our JCasC config, our .p12 keystore,
#                 the 'jenkins-home' data volume, and the
#                 'docker.sock' for DooD.
#  5. HTTPS:      Passes 'JENKINS_OPTS' to enable SSL using
#                 our .p12 keystore and its password.
# -----------------------------------------------------------

set -e
echo "🚀 Deploying Jenkins Controller..."

# --- 1. Define Paths ---
JENKINS_CONFIG_DIR="$HOME/cicd_stack/jenkins/config"
SCOPED_ENV_FILE="$(pwd)/jenkins.env"

# --- 2. Stop and Remove Old Container (if it exists) ---
# This ensures a clean start
if [ "$(docker ps -q -f name=jenkins-controller)" ]; then
    echo "Stopping existing 'jenkins-controller'..."
    docker stop jenkins-controller
fi
if [ "$(docker ps -aq -f name=jenkins-controller)" ]; then
    echo "Removing existing 'jenkins-controller'..."
    docker rm jenkins-controller
fi

# --- 3. Source Keystore Password from Scoped Env File ---
# We need this *one* variable on the host to build the JENKINS_OPTS string
if [ ! -f "$SCOPED_ENV_FILE" ]; then
    echo "⛔ ERROR: Scoped 'jenkins.env' file not found."
    echo "Please run '01-setup-jenkins.sh' first."
    exit 1
fi
# Source the file to load its variables into our script
source "$SCOPED_ENV_FILE"

if [ -z "$JENKINS_KEYSTORE_PASSWORD" ]; then
    echo "⛔ ERROR: JENKINS_KEYSTORE_PASSWORD not found in 'jenkins.env'."
    exit 1
fi

echo "🔐 Keystore password loaded."

# --- 4. Define Ports (from our 01-setup.sh) ---
JENKINS_HTTPS_PORT="10400"
JENKINS_JNLP_PORT="10401"

# --- 5. Run the Controller Container ---
echo "--- Starting 'jenkins-controller' container ---"

docker run -d \
  --name "jenkins-controller" \
  --restart always \
  --network "cicd-net" \
  --hostname "jenkins.cicd.local" \
  --publish "127.0.0.1:${JENKINS_HTTPS_PORT}:${JENKINS_HTTPS_PORT}" \
  --publish "127.0.0.1:${JENKINS_JNLP_PORT}:${JENKINS_JNLP_PORT}" \
  --env-file "$SCOPED_ENV_FILE" \
  --env "CASC_JENKINS_CONFIG=/var/jenkins_home/casc_configs/" \
  --volume "jenkins-home:/var/jenkins_home" \
  --volume "$JENKINS_CONFIG_DIR:/var/jenkins_home/casc_configs:ro" \
  --volume "/var/run/docker.sock:/var/run/docker.sock" \
  --env JENKINS_OPTS="--httpPort=-1 \
--httpsPort=${JENKINS_HTTPS_PORT} \
--httpsKeyStore=/var/jenkins_home/casc_configs/ssl/jenkins.p12 \
--httpsKeyStorePassword=${JENKINS_KEYSTORE_PASSWORD} \
--webroot=/var/jenkins_home/war \
--sessionTimeout=3600 \
--sessionEviction=3600" \
  jenkins-controller:latest

# We no longer override the entrypoint. The image will
# run its default 'jenkins.sh' command.

echo "✅ Jenkins Controller is starting."
echo "   Monitor logs with: docker logs -f jenkins-controller"
echo ""
echo "   Wait for the 'Jenkins is fully up and running' log message."
echo "   Then, access the UI at: https://jenkins.cicd.local:10400"
echo "   (Remember to add '127.0.0.1 jenkins.cicd.local' to your /etc/hosts file!)"