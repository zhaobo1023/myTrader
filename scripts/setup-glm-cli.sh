#!/bin/bash

# Setup GLM-5 CLI wrapper on CentOS
# Provides a command-line interface to GLM-5 API without requiring Node.js
# Usage: ./scripts/setup-glm-cli.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_info() {
    echo -e "${YELLOW}[INFO]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========== GLM-5 CLI Setup =========="
echo ""

# Step 1: Check Python
echo "[1/4] Checking Python..."
if ! command -v python3 &> /dev/null; then
    log_error "Python3 is required but not installed"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
log_ok "Python3 detected: $PYTHON_VERSION"

# Step 2: Install required packages
echo ""
echo "[2/4] Installing Python dependencies..."
pip install -q requests || pip3 install -q requests
log_ok "Python dependencies installed"

# Step 3: Create GLM CLI script
echo ""
echo "[3/4] Creating GLM CLI script..."
mkdir -p ~/.glm

cat > ~/.glm/glm-cli.py << 'PYSCRIPT'
#!/usr/bin/env python3

import os
import sys
import json
import requests

def main():
    api_key = os.getenv('GLM_API_KEY')
    if not api_key:
        print("Error: GLM_API_KEY environment variable not set")
        print("Usage: export GLM_API_KEY='your-api-key'")
        sys.exit(1)

    # Get prompt from command line or stdin
    if len(sys.argv) > 1:
        prompt = ' '.join(sys.argv[1:])
    else:
        prompt = sys.stdin.read()

    if not prompt.strip():
        print("Error: No prompt provided")
        sys.exit(1)

    # Call GLM-5 API
    try:
        response = requests.post(
            'https://open.bigmodel.cn/api/paas/v4/chat/completions',
            json={
                'model': 'glm-4-flash',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 4096,
                'temperature': 0.7
            },
            headers={
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            },
            timeout=300
        )

        if response.status_code == 200:
            result = response.json()
            content = result['choices'][0]['message']['content']
            print(content)
        else:
            print(f"Error: HTTP {response.status_code}")
            print(response.text)
            sys.exit(1)

    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
PYSCRIPT

chmod +x ~/.glm/glm-cli.py
log_ok "GLM CLI script created"

# Step 4: Create symlink
echo ""
echo "[4/4] Creating command symlink..."
if [ -e /usr/local/bin/glm ]; then
    rm /usr/local/bin/glm
fi
ln -s ~/.glm/glm-cli.py /usr/local/bin/glm
log_ok "Command 'glm' is ready"

echo ""
echo "========== Setup Complete =========="
echo ""
echo "Next steps:"
echo ""
echo "1. Set your GLM API Key:"
echo "   export GLM_API_KEY='your-api-key'"
echo "   echo 'export GLM_API_KEY=\"your-api-key\"' >> ~/.bashrc"
echo ""
echo "2. Test GLM CLI:"
echo "   glm 'Hello, how are you?'"
echo ""
echo "3. Read from file:"
echo "   glm < myfile.py 'Analyze this code'"
echo ""
echo "4. Interactive mode (pipe input):"
echo "   cat file.txt | glm 'Summarize this'"
echo ""
