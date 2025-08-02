#!/usr/bin/env python3
"""
Screen Host - Captures and streams screen content
Optimized for low-latency Windows-to-Windows streaming
"""

import socket
import threading
import json
import base64
import zlib
import time
import cv2
import numpy as np
from mss import mss
from PIL import Image
import io

class ScreenHost:
    def __init__(self, host='localhost', port=9999, quality=85, fps=30):
        self.host = host
        self.port = port
        self.quality = quality
        self.fps = fps
        self.frame_delay = 1.0 / fps
        self.clients = []
        self.running = False
        
        # Get monitor info (but don't create mss object here)
        with mss() as sct:
            self.monitor = sct.monitors[1]  # Primary monitor
        print(f"Monitor resolution: {self.monitor['width']}x{self.monitor['height']}")
        
    def capture_screen(self):
        """Capture screen using MSS (fastest method for Windows)"""
        try:
            # Create MSS object in this thread to avoid threading issues
            with mss() as sct:
                # Capture the screen
                screenshot = sct.grab(self.monitor)
                
                # Convert to PIL Image
                img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
                
                # Convert to numpy array for OpenCV
                img_array = np.array(img)
                
                # Encode as JPEG for compression
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), self.quality]
                _, buffer = cv2.imencode('.jpg', img_array, encode_param)
                
                # Compress with zlib for additional size reduction
                compressed = zlib.compress(buffer.tobytes(), level=1)
                
                return compressed
            
        except Exception as e:
            print(f"Screen capture error: {e}")
            return None
    
    def handle_client(self, client_socket, addr):
        """Handle individual client connection"""
        print(f"Client connected from {addr}")
        
        try:
            while self.running:
                # Capture screen
                frame_data = self.capture_screen()
                if frame_data is None:
                    continue
                
                # Prepare frame packet
                frame_packet = {
                    'type': 'frame',
                    'data': base64.b64encode(frame_data).decode('utf-8'),
                    'timestamp': time.time(),
                    'resolution': f"{self.monitor['width']}x{self.monitor['height']}"
                }
                
                # Send frame
                message = json.dumps(frame_packet) + '\n'
                client_socket.send(message.encode('utf-8'))
                
                # Control frame rate
                time.sleep(self.frame_delay)
                
        except Exception as e:
            print(f"Client {addr} error: {e}")
        finally:
            client_socket.close()
            if client_socket in self.clients:
                self.clients.remove(client_socket)
            print(f"Client {addr} disconnected")
    
    def start_server(self):
        """Start the screen streaming server"""
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            self.running = True
            
            print(f"Screen Host started on {self.host}:{self.port}")
            print(f"Streaming at {self.fps} FPS with {self.quality}% quality")
            print("Waiting for clients...")
            
            while self.running:
                try:
                    client_socket, addr = server_socket.accept()
                    self.clients.append(client_socket)
                    
                    # Handle each client in a separate thread
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, addr)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                except socket.error:
                    break
                    
        except Exception as e:
            print(f"Server error: {e}")
        finally:
            server_socket.close()
            self.stop_server()
    
    def stop_server(self):
        """Stop the server and close all connections"""
        self.running = False
        for client in self.clients:
            try:
                client.close()
            except:
                pass
        self.clients.clear()
        print("Screen Host stopped")

if __name__ == "__main__":
    # Configuration
    HOST = 'localhost'  # Change to '0.0.0.0' for network access
    PORT = 9999
    QUALITY = 85  # JPEG quality (1-100)
    FPS = 30      # Frames per second
    
    host = ScreenHost(HOST, PORT, QUALITY, FPS)
    
    try:
        host.start_server()
    except KeyboardInterrupt:
        print("\nShutting down...")
        host.stop_server()