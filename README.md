# WebRTC Screen Streaming Module

A professional-grade, low-latency screen streaming solution with NAT traversal support. Built with WebRTC for real-world deployment across networks, firewalls, and NATs.

## Features

- **WebRTC with NAT Traversal**: Works across firewalls and NATs using STUN servers
- **Signaling Server**: Handles peer discovery and WebRTC negotiation
- **Low Latency**: Optimized WebRTC streaming with minimal buffering
- **High Quality**: Real-time screen capture with efficient encoding
- **Multi-Client Support**: Multiple clients can connect to one host
- **Room-based**: Organize connections by room IDs
- **Cross-Network**: Works on local networks and across the internet
- **Fallback Support**: Legacy TCP version included for local networks

## Quick Start

### 1. Setup
```bash
python setup.py
```

### 2. Start the Signaling Server
```bash
python signaling_server.py
```

### 3. Start the Host (Screen Sharing Device)
```bash
python webrtc_host.py
```

### 4. Start the Client (Viewing Device)
```bash
python webrtc_client.py
```

## Configuration

### WebRTC Configuration
- **Signaling Server**: Default `ws://localhost:8765`
- **Room ID**: Default 'default', use custom rooms for isolation
- **STUN Servers**: Google STUN servers configured by default
- **Video Quality**: 30 FPS with optimized encoding

### Command Line Options
```bash
# Custom signaling server and room
python webrtc_host.py --signaling ws://your-server.com:8765 --room myroom
python webrtc_client.py --signaling ws://your-server.com:8765 --room myroom
```

## Controls (Client)
- **Q or ESC**: Quit the client
- **F**: Toggle fullscreen mode
- **W**: Return to windowed mode

## Deployment

### Local Network
The signaling server runs on localhost by default. Both host and client will automatically discover each other through the signaling server.

### Internet Access
1. **Deploy Signaling Server**: Run `signaling_server.py` on a public server
2. **Update URLs**: Point both host and client to your signaling server
3. **Firewall**: Ensure port 8765 (signaling) is open on your server
4. **NAT Traversal**: WebRTC handles NAT/firewall traversal automatically

### Production Deployment
```bash
# On your public server
python signaling_server.py

# On host machine
python webrtc_host.py --signaling ws://your-server.com:8765

# On client machine  
python webrtc_client.py --signaling ws://your-server.com:8765
```

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

### WebRTC Implementation
- **Screen Capture**: MSS (Multi-Screen Shot) for fastest Windows capture
- **Video Encoding**: Hardware-accelerated encoding via aiortc/libav
- **Transport**: WebRTC with ICE/STUN for NAT traversal
- **Signaling**: WebSocket-based signaling server
- **Display**: OpenCV with minimal buffering for low latency

### Network Architecture
- **Signaling**: WebSocket server for peer discovery and SDP exchange
- **Media**: Direct P2P WebRTC connection between host and clients
- **NAT Traversal**: STUN servers handle most NAT scenarios
- **Fallback**: TURN server support can be added for restrictive networks

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