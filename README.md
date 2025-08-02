# Screen Streaming Module

A low-latency, high-quality screen streaming solution for Windows-to-Windows remote control. This module allows you to share your screen over a network connection with optimized performance.

## Features

- **Low Latency**: Optimized for minimal delay using efficient capture and compression
- **High Quality**: Configurable JPEG quality with zlib compression
- **Multi-Client Support**: Multiple clients can connect to one host simultaneously
- **Real-time Stats**: FPS counter and connection monitoring
- **Keyboard Controls**: Fullscreen toggle and easy exit options
- **Network Ready**: Easy configuration for local network or internet access

## Quick Start

### 1. Setup
```bash
python setup.py
```

### 2. Start the Host (Screen Sharing Device)
```bash
python screen_host.py
```

### 3. Start the Client (Viewing Device)
```bash
python screen_client.py
```

## Configuration

### Host Configuration (screen_host.py)
- `HOST`: Set to 'localhost' for local testing, '0.0.0.0' for network access
- `PORT`: Default 9999, change if needed
- `QUALITY`: JPEG quality 1-100 (85 recommended)
- `FPS`: Frames per second (30 recommended)

### Client Configuration (screen_client.py)
- `HOST`: IP address of the host machine
- `PORT`: Must match host port

## Controls (Client)
- **Q or ESC**: Quit the client
- **F**: Toggle fullscreen mode
- **W**: Return to windowed mode

## Network Setup

### Local Network Access
1. On host machine, change `HOST = '0.0.0.0'` in screen_host.py
2. On client machine, change `HOST = 'HOST_IP_ADDRESS'` in screen_client.py
3. Ensure Windows Firewall allows the application through port 9999

### Internet Access (Advanced)
1. Configure port forwarding on your router for port 9999
2. Use your public IP address on the client
3. Consider security implications and use VPN when possible

## Performance Optimization

### For Better Performance:
- Lower FPS (20-25) for slower connections
- Reduce QUALITY (70-80) for bandwidth-limited scenarios
- Close unnecessary applications on host machine

### For Better Quality:
- Increase QUALITY (90-95) for high-bandwidth connections
- Increase FPS (60) for smoother motion
- Use wired network connections when possible

## Technical Details

- **Screen Capture**: MSS (Multi-Screen Shot) for fastest Windows capture
- **Compression**: JPEG encoding + zlib compression
- **Transport**: TCP sockets with JSON framing
- **Display**: OpenCV for cross-platform compatibility
- **Threading**: Separate threads for capture, transmission, and display

## Troubleshooting

### Common Issues:
1. **Connection Refused**: Check if host is running and firewall settings
2. **Poor Performance**: Reduce FPS or quality settings
3. **Black Screen**: Try running as administrator
4. **High CPU Usage**: Lower FPS or quality, close other applications

### System Requirements:
- Python 3.7+
- Windows (optimized, but works on other platforms)
- At least 4GB RAM recommended
- Network connection (local or internet)

## Future Enhancements

This module is part of a larger remote control framework. Planned features:
- Mouse and keyboard input forwarding
- File transfer capabilities
- Wake-on-LAN support
- Authentication and encryption
- Mobile app clients
- Cross-platform optimization

## License

This project is part of a personal remote control framework. Use responsibly and ensure you have permission to access remote systems.