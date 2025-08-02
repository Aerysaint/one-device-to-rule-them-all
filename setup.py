#!/usr/bin/env python3
"""
Setup script for the screen streaming module
"""

import subprocess
import sys
import os

def install_requirements():
    """Install required packages"""
    print("Installing required packages...")
    
    requirements = [
        "opencv-python==4.8.1.78",
        "numpy==1.24.3", 
        "Pillow==10.0.1",
        "mss==9.0.1"
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
    print("To start the host (screen sharing): python screen_host.py")
    print("To start the client (screen viewing): python screen_client.py")
    print("\nFor network access, edit the HOST variable in both files")
    
    return True

if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)