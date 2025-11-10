#!/usr/bin/env python3

import os
import ssl
import json
import urllib.request
import urllib.parse
from pathlib import Path

# --- Configuration ---
ENV_FILE_PATH = Path.cwd() / "jenkins.env"
JENKINS_URL = "https://jenkins:10400"
JENKINS_USER = "admin"

# --- 1. Standard Library .env parser ---
def load_env(env_path):
    """
    Reads a .env file and loads its variables into os.environ.
    """
    print(f"Loading environment from: {env_path}")
    if not env_path.exists():
        print(f"⛔ ERROR: Environment file not found at {env_path}")
        print("Please run '01-setup-jenkins.sh' first.")
        return False

    with open(env_path, 'r') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip().strip('"\'')
                os.environ[key] = value
    return True

# --- 2. Main Verification ---
def verify_jenkins_api(base_url, username, password):
    """
    Connects to Jenkins, gets a CSRF crumb, and attempts
    an authenticated API call.
    """

    # This is the "Payoff" from Article 2.
    # Python will use the host's system trust store,
    # which we already configured to trust our Local CA.
    print("Creating default SSL context...")
    context = ssl.create_default_context()

    # --- 3. Setup Password Manager for Auth ---
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, base_url, username, password)

    # We need two handlers: one for auth, one for SSL
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_mgr)
    https_handler = urllib.request.HTTPSHandler(context=context)

    opener = urllib.request.build_opener(auth_handler, https_handler)
    urllib.request.install_opener(opener)

    # --- 4. Fetch CSRF Crumb ---
    # Jenkins requires a CSRF crumb for all POST requests.
    print(f"Connecting to {base_url} to fetch CSRF crumb...")
    crumb_url = f"{base_url}/crumbIssuer/api/json"

    try:
        with urllib.request.urlopen(crumb_url) as response:
            if response.status != 200:
                print(f"⛔ ERROR: Failed to get crumb. Status: {response.status}")
                return False

            crumb_data = json.loads(response.read().decode())
            crumb = crumb_data["crumb"]
            crumb_header = crumb_data["crumbRequestField"]
            print(f"✅ Success! Got CSRF crumb: {crumb}")

    except urllib.error.URLError as e:
        print(f"⛔ ERROR: Connection failed. Did you add '127.0.0.1 jenkins' to /etc/hosts?")
        print(f"   Details: {e}")
        return False
    except Exception as e:
        print(f"⛔ ERROR: An unknown error occurred: {e}")
        return False

    # --- 5. Make an Authenticated API Call ---
    # We will run a simple Groovy script to test our auth.
    print("Attempting authenticated API call (Groovy script)...")
    script_url = f"{base_url}/scriptText"

    # This simple script just tests the connection.
    groovy_script = "return jenkins.model.Jenkins.get().getSystemMessage()"

    data = urllib.parse.urlencode({'script': groovy_script}).encode('utf-8')

    headers = {
        crumb_header: crumb,
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    req = urllib.request.Request(script_url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req) as response:
            if response.status == 200:
                result = response.read().decode()
                print(f"✅✅✅ Jenkins Verification SUCCESS! ✅✅✅")
                print(f"Authenticated API call returned: {result}")
            else:
                print(f"⛔ ERROR: API call failed. Status: {response.status}")
                print(f"   Response: {response.read().decode()}")

    except Exception as e:
        print(f"⛔ ERROR: API call failed.")
        print(f"   Details: {e}")

# --- 6. Main execution ---
if __name__ == "__main__":
    if not load_env(ENV_FILE_PATH):
        exit(1)

    JENKINS_PASSWORD = os.getenv('JENKINS_ADMIN_PASSWORD')

    if not JENKINS_PASSWORD:
        print("⛔ ERROR: JENKINS_ADMIN_PASSWORD not found in 'jenkins.env'")
        exit(1)

    verify_jenkins_api(JENKINS_URL, JENKINS_USER, JENKINS_PASSWORD)