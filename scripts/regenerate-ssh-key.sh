#!/bin/bash

# Regenerate SSH Key on ECS
# Delete old key + Generate new key + Display public key for GitHub

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_ok() {
    echo -e "${GREEN}[OK]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

echo "========== SSH Key Regeneration =========="
echo ""

# Step 1: Backup old key
echo "[1] Backing up old SSH key..."
if [ -d ~/.ssh ]; then
    BACKUP_DIR=~/.ssh.backup.$(date +%Y%m%d_%H%M%S)
    mv ~/.ssh "$BACKUP_DIR"
    log_ok "Old key backed up to: $BACKUP_DIR"
else
    log_warn "~/.ssh does not exist, skipping backup"
fi

# Step 2: Create .ssh directory
echo ""
echo "[2] Creating .ssh directory..."
mkdir -p ~/.ssh
chmod 700 ~/.ssh
log_ok "Directory created with correct permissions"

# Step 3: Get GitHub email
echo ""
echo "[3] GitHub email required..."
read -p "Enter your GitHub email address (e.g., your-email@example.com): " GIT_EMAIL

if [ -z "$GIT_EMAIL" ]; then
    log_error "Email cannot be empty"
    exit 1
fi

log_ok "Email: $GIT_EMAIL"

# Step 4: Generate ED25519 SSH key (modern)
echo ""
echo "[4] Generating SSH key (ED25519)..."
ssh-keygen -t ed25519 \
    -C "$GIT_EMAIL" \
    -f ~/.ssh/id_ed25519 \
    -N ""

log_ok "ED25519 key generated"

# Step 5: Generate RSA backup key (compatibility)
echo ""
echo "[5] Generating backup key (RSA 4096)..."
ssh-keygen -t rsa \
    -b 4096 \
    -C "$GIT_EMAIL" \
    -f ~/.ssh/id_rsa \
    -N ""

log_ok "RSA key generated"

# Step 6: Display public key
echo ""
echo "========== Key Generation Complete =========="
echo ""
echo "[6] ED25519 Public Key (recommended for GitHub):"
echo "=================================================="
cat ~/.ssh/id_ed25519.pub
echo "=================================================="
echo ""

echo "[7] RSA Public Key (backup):"
echo "=================================================="
cat ~/.ssh/id_rsa.pub
echo "=================================================="
echo ""

# Step 8: Set key permissions
echo "[8] Setting key permissions..."
chmod 600 ~/.ssh/id_ed25519
chmod 600 ~/.ssh/id_rsa
chmod 644 ~/.ssh/id_ed25519.pub
chmod 644 ~/.ssh/id_rsa.pub
log_ok "Permissions set correctly"

# Step 9: Create SSH config
echo ""
echo "[9] Creating SSH configuration..."
cat > ~/.ssh/config << 'EOF'
Host github.com
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519
    IdentityFile ~/.ssh/id_rsa
    AddKeysToAgent yes
    StrictHostKeyChecking accept-new
EOF

chmod 600 ~/.ssh/config
log_ok "SSH config created"

echo ""
echo "========== Next Steps =========="
echo ""
echo "1. Copy the ED25519 public key above"
echo ""
echo "2. Go to GitHub to add the key:"
echo "   https://github.com/settings/keys"
echo ""
echo "3. Click 'New SSH key'"
echo ""
echo "4. Fill in the information:"
echo "   Title: ECS Production"
echo "   Key: Paste the ED25519 public key above"
echo ""
echo "5. Click 'Add SSH key'"
echo ""
echo "6. Verify on ECS:"
echo "   ssh -T git@github.com"
echo ""
echo "7. Test git pull:"
echo "   cd /opt/myTrader"
echo "   git pull origin main"
echo ""
