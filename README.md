# Steam Deck Robot Control System

A Python-based robot control system that enables real-time remote control using a gamepad, with LoRa communication, live camera streaming, and telemetry monitoring.

## Quick Start

```bash
# Clone the repository
git clone <repository-url>
cd control_steamdeck

# Run automated setup
chmod +x setup.sh
./setup.sh

# Start the system
./run.sh
```

For detailed instructions, see the [Installation](#installation) section below.

## Overview

This project provides a complete solution for controlling a robot remotely using a gamepad controller. It features bidirectional LoRa communication for command transmission and heartbeat monitoring, real-time camera streaming over WebSocket, and comprehensive telemetry data broadcasting for monitoring robot status.

## Features

### Control System
- **Gamepad Input**: Full support for gamepad controllers with automatic device detection
- **Dual-axis Control**: Forward/backward (v) and rotation (w) control with configurable dead zones
- **Mode Management**: 
  - Sleep Mode: Pause all command transmission (L1 + R1 combo)
  - Speed+ Mode: Toggle between normal and high-speed operation (L2 + R2 combo)
- **Configurable Scaling**: Adjustable speed multipliers for different operation modes

### Communication
- **LoRa Link**: Reliable serial communication with automatic heartbeat monitoring
- **Heartbeat System**: Connection health tracking with automatic timeout detection
- **Command Transmission**: Configurable transmission rate (default: 10 Hz)

### Video Streaming
- **Live Camera Feed**: Real-time MJPEG streaming over WebSocket
- **Low Latency**: Optimized for minimal delay with buffer size management
- **Adjustable Quality**: Configurable JPEG compression for bandwidth optimization
- **Multi-client Support**: Multiple viewers can connect simultaneously

### Telemetry
- **Real-time Monitoring**: WebSocket-based telemetry broadcasting
- **Link Quality Metrics**: Connection health, heartbeat age, and transmission rate
- **Robot State**: Current velocity commands, active modes, and system status
- **Sensor Placeholders**: Framework for battery, temperature, and air quality sensors

## Hardware Requirements

- **Computing Device**: Linux-based system (tested on Steam Deck)
- **Camera**: USB camera or V4L2-compatible video device (`/dev/video0`)
- **Gamepad**: Compatible game controller with analog sticks
  - Supported buttons: L1 (BTN_TL), R1 (BTN_TR), L2 (BTN_TL2), R2 (BTN_TR2)
  - Required axes: Left stick Y-axis (ABS_Y), Right stick X-axis (ABS_RX/ABS_Z/ABS_RY)
- **LoRa Module**: USB serial LoRa transceiver (e.g., `/dev/ttyUSB0` or `/dev/ttyACM0`)

## Software Requirements

### Operating System
- **Linux** (required)
  - Native Linux distributions
  - Steam Deck (SteamOS)
  - WSL2 on Windows (with USB passthrough)

### Python Version
- Python 3.10 or higher

### Dependencies
- `opencv-python` (cv2): Video capture and JPEG encoding
- `websockets`: WebSocket server implementation
- `pyserial`: Serial port communication
- `evdev`: Linux input device event handling
- `numpy`: Array operations for image processing

### Installation

#### Option 1: Automated Setup (Recommended)

1. Clone the repository:
```bash
git clone <repository-url>
cd control_steamdeck
```

2. Run the setup script:
```bash
chmod +x setup.sh
./setup.sh
```

The script will:
- Create a virtual environment if it doesn't exist
- Install all dependencies from `requirements.txt`
- Set up user permissions for device access
- Check for connected devices (camera, serial ports)
- Create a convenient `run.sh` script

3. Log out and back in if groups were added

#### Option 2: Manual Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd control_steamdeck
```

2. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Ensure proper permissions for device access:
```bash
# Add user to input and dialout groups
sudo usermod -a -G input,dialout $USER
# Log out and back in for changes to take effect
```

## Configuration

The system is configured via `config.json`. All parameters have sensible defaults.

### Configuration File Structure

```json
{
  "serial": {
    "port": "auto",           // Serial port path or "auto" for detection
    "baud": 9600             // Baud rate for LoRa communication
  },
  "joystick": {
    "device": "auto",         // Input device path or "auto" for detection
    "dead_zone": 0.05,        // Analog stick dead zone (0.0-1.0)
    "invert_v": false,        // Invert forward/backward axis
    "invert_w": false,        // Invert rotation axis
    "right_axis_candidates": ["ABS_RX", "ABS_Z", "ABS_RY"]
  },
  "tx": {
    "max_rate_hz": 10,        // Command transmission rate (Hz)
    "hb_timeout_sec": 15.0    // Heartbeat timeout threshold (seconds)
  },
  "protocol": {
    "hb_msg": "READY",                // Heartbeat message from robot
    "timeout_msg": "TIMEOUT",         // Timeout notification message
    "timeout_clear_msg": "TIMEOUT_CLEAR"
  },
  "modes": {
    "start_sleep": true,             // Start in sleep mode
    "combo_hold_sec": 3.0,           // Button combo hold time (seconds)
    "speed_default_scale": 0.70,     // Normal speed multiplier
    "speed_plus_scale": 1.00         // Speed+ multiplier
  },
  "ws": {
    "host": "0.0.0.0",        // WebSocket bind address
    "port": 8080,             // WebSocket port
    "publish_hz": 2.0         // Telemetry broadcast rate (Hz)
  }
}
```

### Auto-Detection

Both serial port and gamepad device can be set to `"auto"` for automatic detection:
- **Serial Port**: Searches for `/dev/ttyUSB*` and `/dev/ttyACM*` devices
- **Gamepad**: Looks for devices with required analog axes, preferring Steam Deck's built-in controller

## Usage

### Starting the System

#### If you used the automated setup:
```bash
./run.sh
```

#### Manual start:
1. Activate the virtual environment:
```bash
source venv/bin/activate
```

2. Run the main control program:
```bash
python main.py
```

Or make it executable:
```bash
chmod +x main.py
./main.py
```

### Expected Output

```
* Serial: /dev/ttyUSB0 @ 9600
* Gamepad: OpenSD Controller @ /dev/input/event7
  Using ABS_Y for v and ABS_RX for w
WS up on ws://0.0.0.0:8080 (routes: /telemetry, /rgb_camera)
```

### Gamepad Controls

- **Left Stick (Y-axis)**: Forward/backward movement
- **Right Stick (X-axis)**: Rotation/turning
- **L1 + R1 (hold 3s)**: Toggle Sleep Mode (stops all transmissions)
- **L2 + R2 (hold 3s)**: Toggle Speed+ Mode (full speed vs. 70% speed)

### WebSocket Endpoints

#### Telemetry Stream
```
ws://<host>:8080/telemetry
```

Receives JSON messages every 0.5 seconds (configurable):
```json
{
  "type": "telemetry",
  "timestamp": 1697371234567,
  "sleep": false,
  "speed_plus": false,
  "lora_connected": true,
  "link_quality": 95,
  "tx_rate_hz": 10.0,
  "rx_hb_age_s": 1.234,
  "v": 0.850,
  "w": -0.320,
  "battery_pct": 100,
  "temperature_c": 25,
  "air_quality": 95
}
```

#### Camera Stream
```
ws://<host>:8080/rgb_camera
```

Receives binary JPEG frames at maximum possible rate (typically 20-30 FPS).

### Standalone Components

Individual components can be run separately for testing:

#### Camera Streaming Only
```bash
python camera_start.py
```
Starts camera WebSocket server on port 8765 at `/rgb_camera`

#### Telemetry Server Test
```bash
python telemetry_ws.py
```

#### Joystick Test
```bash
python joystick_test.py
```
Displays raw joystick values and button states

## Project Structure

```
control_steamdeck/
├── main.py              # Main unified control system
├── config.json          # Configuration file
├── config_loader.py     # Configuration parser and dataclasses
├── joystick.py          # Gamepad input handler
├── lora.py              # LoRa serial communication
├── camera_start.py      # Standalone camera WebSocket server
├── telemetry_ws.py      # Telemetry WebSocket server class
├── joystick_test.py     # Gamepad testing utility
├── requirements.txt     # Python dependencies
├── setup.sh             # Automated setup script
├── run.sh               # Convenience script (created by setup.sh)
├── .gitignore           # Git ignore rules
└── test/                # Test scripts
    ├── lora_test.py     # LoRa communication tests
    ├── motor_test.py    # Motor control tests
    ├── sensorRead_test.py
    └── test_camera.py   # Camera functionality tests
```

## Module Details

### main.py
Unified entry point that combines all components:
- Initializes serial connection and gamepad
- Manages dual-mode operation (sleep/speed+)
- Runs command transmission loop
- Hosts both telemetry and camera WebSocket endpoints on single port

### joystick.py
Gamepad input handling using evdev:
- Auto-detection of compatible controllers
- Axis normalization with dead zone
- Button state tracking
- Asynchronous event reading

### lora.py
Serial communication manager:
- Auto-detection of serial ports
- Background thread for RX processing
- Heartbeat tracking
- Line-based protocol

### camera_start.py
Video streaming implementation:
- V4L2 camera capture with OpenCV
- JPEG compression
- Frame hub with queue management
- Zero-lag streaming architecture

### config_loader.py
Configuration management:
- JSON parsing with defaults
- Type-safe dataclasses
- Deep merge for partial configs

### setup.sh
Automated setup script:
- Virtual environment creation
- Dependency installation
- User permission configuration (dialout and input groups)
- Device detection and validation (camera, serial ports)
- Creates convenience run script

### requirements.txt
Python package dependencies with version constraints for reproducible builds

## Communication Protocol

### Command Format (TX)
Commands are sent as CSV strings:
```
<v>,<w>\r\n
```
- `v`: Forward velocity (-1.0 to +1.0)
- `w`: Angular velocity (-1.0 to +1.0)

### Heartbeat Format (RX)
The robot should periodically send:
```
READY\r\n
```

### Timeout Behavior
- If no heartbeat received for `hb_timeout_sec`, transmission stops automatically
- Link quality degrades linearly based on heartbeat age
- System continues monitoring; resumes when heartbeat returns

## Troubleshooting

### Serial Port Issues
**Problem**: "Seri port bulunamadı" (Serial port not found)
- Verify LoRa module is connected: `ls /dev/ttyUSB* /dev/ttyACM*`
- Check USB cable and connection
- Ensure user has permissions: `groups $USER` should show `dialout`

### Gamepad Not Detected
**Problem**: "Gamepad açılamadı" (Gamepad not detected)
- List input devices: `ls /dev/input/by-id/`
- Verify controller is connected
- Check permissions: user should be in `input` group
- Try specifying device path explicitly in config

### Camera Issues
**Problem**: "Cannot open camera"
- Check camera device: `ls /dev/video*`
- Test with: `v4l2-ctl --list-devices`
- Verify camera is not in use by another application
- Try different device in `main.py` (change `DEVICE` variable)

### WebSocket Connection Fails
- Verify firewall allows port 8080
- Check if port is already in use: `ss -tlnp | grep 8080`
- Try different port in `config.json`

### Low Frame Rate
- Reduce JPEG quality (lower `JPEG_QUALITY` in `main.py`)
- Check network bandwidth
- Reduce camera resolution (`SRC_W`, `SRC_H`)

## Performance Notes

- **Command Latency**: Typically <10ms from gamepad to LoRa TX
- **Camera Latency**: 50-100ms with default settings
- **Bandwidth**: ~100-500 KB/s per camera client (depends on quality setting)
- **CPU Usage**: Moderate; ~10-20% on modern hardware

## Future Enhancements

- Real sensor integration (battery, IMU, temperature)
- Multiple camera support
- Recording/playback functionality
- GUI dashboard for telemetry visualization
- Autonomous navigation modes
- Configurable button mappings

## License

[Add your license information here]

## Authors

[Add author information here]

## Contributing

[Add contribution guidelines here]


