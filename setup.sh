#!/bin/bash

# Steam Deck Robot Control - Setup Script
# This script creates a virtual environment, installs dependencies, and sets up permissions

set -e  # Exit on error

echo "========================================="
echo "Steam Deck Robot Control - Setup"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"
echo ""

# Create virtual environment if it doesn't exist
VENV_DIR="venv"
if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment already exists at ./$VENV_DIR"
else
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment created successfully."
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source "$VENV_DIR/bin/activate"
echo "Virtual environment activated."
echo ""

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip
echo ""

# Install dependencies
echo "Installing dependencies from requirements.txt..."
pip install -r requirements.txt
echo ""
echo "Dependencies installed successfully."
echo ""

# Check if running on Steam Deck
if [ -f "/etc/os-release" ]; then
    if grep -q "Steam" /etc/os-release 2>/dev/null; then
        echo "Steam Deck detected!"
        echo ""
    fi
fi

echo "Checking user permissions..."
CURRENT_USER=$(whoami)

# Check dialout group (for serial port access)
if groups "$CURRENT_USER" | grep -q "\bdialout\b"; then
    echo "✓ User is already in 'dialout' group (serial port access)"
else
    echo "✗ User is NOT in 'dialout' group"
    echo "  Adding user to dialout group..."
    sudo usermod -a -G dialout "$CURRENT_USER" || echo "  Warning: Failed to add user to dialout group. You may need to do this manually."
fi

# Check input group (for gamepad access)
if groups "$CURRENT_USER" | grep -q "\binput\b"; then
    echo "✓ User is already in 'input' group (gamepad access)"
else
    echo "✗ User is NOT in 'input' group"
    echo "  Adding user to input group..."
    sudo usermod -a -G input "$CURRENT_USER" || echo "  Warning: Failed to add user to input group. You may need to do this manually."
fi

echo ""
echo "Note: If groups were added, you need to log out and back in"
echo "      (or restart) for the changes to take effect."
echo ""

# Check for camera device
if ls /dev/video* 1> /dev/null 2>&1; then
    echo "✓ Camera device(s) found:"
    ls -l /dev/video* | awk '{print "  " $NF}'
else
    echo "⚠ No camera devices found at /dev/video*"
fi
echo ""

# Check for serial devices
if ls /dev/ttyUSB* /dev/ttyACM* 1> /dev/null 2>&1; then
    echo "✓ Serial device(s) found:"
    (ls -l /dev/ttyUSB* 2>/dev/null || true) | awk '{print "  " $NF}'
    (ls -l /dev/ttyACM* 2>/dev/null || true) | awk '{print "  " $NF}'
else
    echo "⚠ No serial devices found (LoRa module may not be connected)"
fi
echo ""

# Create a run script
echo "Creating run script..."
cat > run.sh << 'EOF'
#!/bin/bash
# Activate virtual environment and run main.py

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ ! -d "venv" ]; then
    echo "Error: Virtual environment not found. Please run setup.sh first."
    exit 1
fi

source venv/bin/activate
python main.py "$@"
EOF

chmod +x run.sh
echo "Created run.sh script."
echo ""

echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "To run the program:"
echo "  1. Activate the virtual environment:"
echo "     source venv/bin/activate"
echo ""
echo "  2. Run the main program:"
echo "     python main.py"
echo ""
echo "  OR use the convenience script:"
echo "     ./run.sh"
echo ""
echo "To deactivate the virtual environment later:"
echo "     deactivate"
echo ""

