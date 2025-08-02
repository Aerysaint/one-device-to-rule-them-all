#!/usr/bin/env python3
"""
Setup script for the WebRTC screen streaming module
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("Installing required packages...")
    
    requirements = [
        "aiortc==1.6.0",
        "opencv-python==4.8.1.78",
        "numpy==1.24.3", 
        "Pillow==10.0.1",
        "mss==9.0.1",
        "websockets==11.0.3",
        "aiohttp==3.9.1",
        "av==10.0.0"
    ]
    
    for package in requirements:
        try:
            print(f"Installing {package}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        except subprocess.CalledProcessError as e:
            print(f"Failed to install {package}: {e}")
            return False
    
    print("All packages installed successfully!")
    return True

def check_system():
    """Check system requirements"""
    print("Checking system requirements...")
    
    # Check Python version
    if sys.version_info < (3, 7):
        print("Error: Python 3.7 or higher is required")
        return False
    
    print(f"Python version: {sys.version}")
    
    # Check if we're on Windows
    if os.name != 'nt':
        print("Warning: This module is optimized for Windows")
    
    return True

def main():
    """Main setup function"""
    print("=== Screen Streaming Module Setup ===")
    
    if not check_system():
        return False
    
    if not install_requirements():
        return False
    
    print("\n=== Setup Complete ===")
    print("WebRTC Screen Streaming Setup:")
    print("1. Start signaling server: python signaling_server.py")
    print("2. Start host (screen sharing): python webrtc_host.py")
    print("3. Start client (screen viewing): python webrtc_client.py")
    print("\nFor internet access, deploy signaling server on public server")
    print("Legacy TCP version also available: screen_host.py & screen_client.py")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)