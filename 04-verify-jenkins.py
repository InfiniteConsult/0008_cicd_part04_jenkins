#!/usr/bin/env python3

import os
import ssl
import json
import urllib.request
import urllib.parse
import base64  # <--- IMPORT THIS
from pathlib import Path


ENV_FILE_PATH = Path.cwd() / "jenkins.env"
JENKINS_URL = "https://jenkins.cicd.local:10400"
JENKINS_USER = "admin"


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


def verify_jenkins_api(base_url, username, api_token):
    """
    Connects to Jenkins using a manually-crafted Basic Auth
    header (token) and attempts an authenticated API call.
    This method does not use or need a CSRF crumb.
    """

    print("Creating default SSL context...")
    context = ssl.create_default_context()

    print("Attempting authenticated API call (Groovy script)...")
    script_url = f"{base_url}/scriptText"

    groovy_script = "return jenkins.model.Jenkins.get().getSystemMessage()"
    data = urllib.parse.urlencode({'script': groovy_script}).encode('utf-8')

    auth_string = f"{username}:{api_token}"
    auth_bytes = auth_string.encode('utf-8')
    auth_base64 = base64.b64encode(auth_bytes).decode('ascii')

    headers = {
        'Authorization': f"Basic {auth_base64}",
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    req = urllib.request.Request(script_url, data=data, headers=headers, method='POST')

    try:
        with urllib.request.urlopen(req, context=context) as response:
            if response.status == 200:
                result = response.read().decode()
                print(f"✅✅✅ Jenkins Verification SUCCESS! ✅✅✅")
                print(f"Authenticated API call returned: {result}")
            else:
                print(f"⛔ ERROR: API call failed. Status: {response.status}")
                print(f"   Response: {response.read().decode()}")

    except urllib.error.URLError as e:
        print(f"⛔ ERROR: Connection failed. Did you add '127.0.0.1 jenkins.cicd.local' to /etc/hosts?")
        print(f"   Details: {e}")
        if hasattr(e, 'read'):
            print(f"  Response: {e.read().decode()}")
    except Exception as e:
        print(f"⛔ ERROR: API call failed.")
        print(f"   Details: {e}")
        if hasattr(e, 'read'):
            print(f"  Response: {e.read().decode()}")


if __name__ == "__main__":
    if not load_env(ENV_FILE_PATH):
        exit(1)

    JENKINS_TOKEN = os.getenv('JENKINS_API_TOKEN')

    if not JENKINS_TOKEN:
        print("⛔ ERROR: JENKINS_API_TOKEN not found in 'jenkins.env'")
        print("Please generate one in the UI and add it to the file.")
        exit(1)

    verify_jenkins_api(JENKINS_URL, JENKINS_USER, JENKINS_TOKEN)