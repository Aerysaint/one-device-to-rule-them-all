#!/usr/bin/env python3
"""
Screen Client - Receives and displays streamed screen content
Optimized for low-latency Windows-to-Windows streaming
"""

import socket
import json
import base64
import zlib
import cv2
import numpy as np
import threading
import time
from collections import deque

class ScreenClient:
    def __init__(self, host='localhost', port=9999):
        self.host = host
        self.port = port
        self.running = False
        self.socket = None
        self.frame_buffer = deque(maxlen=2)  # Small buffer to reduce latency
        self.stats = {
            'frames_received': 0,
            'frames_displayed': 0,
            'last_fps_check': time.time(),
            'fps': 0
        }
        
    def connect_to_host(self):
        """Connect to the screen host"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self.running = True
            print(f"Connected to screen host at {self.host}:{self.port}")
            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            return False
    
    def receive_frames(self):
        """Receive frames from host in a separate thread"""
        buffer = ""
        
        while self.running:
            try:
                # Receive data
                data = self.socket.recv(4096).decode('utf-8')
                if not data:
                    break
                
                buffer += data
                
                # Process complete JSON messages
                while '\n' in buffer:
                    line, buffer = buffer.split('\n', 1)
                    if line.strip():
                        try:
                            frame_packet = json.loads(line)
                            if frame_packet['type'] == 'frame':
                                # Decode and decompress frame
                                compressed_data = base64.b64decode(frame_packet['data'])
                                frame_data = zlib.decompress(compressed_data)
                                
                                # Convert to numpy array
                                nparr = np.frombuffer(frame_data, np.uint8)
                                frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
                                
                                if frame is not None:
                                    # Add to buffer (will automatically remove old frames)
                                    self.frame_buffer.append({
                                        'frame': frame,
                                        'timestamp': frame_packet['timestamp'],
                                        'resolution': frame_packet['resolution']
                                    })
                                    self.stats['frames_received'] += 1
                                    
                        except json.JSONDecodeError:
                            continue
                        except Exception as e:
                            print(f"Frame processing error: {e}")
                            continue
                            
            except Exception as e:
                print(f"Receive error: {e}")
                break
    
    def display_frames(self):
        """Display frames using OpenCV"""
        cv2.namedWindow('Remote Screen', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('Remote Screen', 1280, 720)  # Initial size
        
        while self.running:
            if self.frame_buffer:
                # Get the latest frame
                frame_data = self.frame_buffer.popleft()
                frame = frame_data['frame']
                
                # Display frame
                cv2.imshow('Remote Screen', frame)
                self.stats['frames_displayed'] += 1
                
                # Update FPS counter
                current_time = time.time()
                if current_time - self.stats['last_fps_check'] >= 1.0:
                    self.stats['fps'] = self.stats['frames_displayed']
                    self.stats['frames_displayed'] = 0
                    self.stats['last_fps_check'] = current_time
                    
                    # Update window title with stats
                    title = f"Remote Screen - {frame_data['resolution']} - {self.stats['fps']} FPS"
                    cv2.setWindowTitle('Remote Screen', title)
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC to quit
                    self.running = False
                    break
                elif key == ord('f'):  # 'f' for fullscreen toggle
                    # Toggle fullscreen (basic implementation)
                    cv2.setWindowProperty('Remote Screen', cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_FULLSCREEN)
                elif key == ord('w'):  # 'w' for windowed mode
                    cv2.setWindowProperty('Remote Screen', cv2.WND_PROP_FULLSCREEN, 
                                        cv2.WINDOW_NORMAL)
            else:
                # No frames available, small delay
                time.sleep(0.001)
        
        cv2.destroyAllWindows()
    
    def start_client(self):
        """Start the screen client"""
        if not self.connect_to_host():
            return
        
        print("Starting screen client...")
        print("Controls:")
        print("  Q or ESC - Quit")
        print("  F - Fullscreen")
        print("  W - Windowed mode")
        
        # Start frame receiving thread
        receive_thread = threading.Thread(target=self.receive_frames)
        receive_thread.daemon = True
        receive_thread.start()
        
        # Start display loop (main thread)
        try:
            self.display_frames()
        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.stop_client()
    
    def stop_client(self):
        """Stop the client and close connection"""
        self.running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        print("Screen Client stopped")

if __name__ == "__main__":
    # Configuration
    HOST = '192.168.5.80'  # Change to host IP for network access
    PORT = 9999
    
    client = ScreenClient(HOST, PORT)
    
    try:
        client.start_client()
    except KeyboardInterrupt:
        print("\nShutting down...")
        client.stop_client()