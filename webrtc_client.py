#!/usr/bin/env python3
"""
WebRTC Screen Client - Receives and displays WebRTC screen stream
Supports NAT traversal with STUN/TURN servers
"""

import asyncio
import json
import logging
import uuid
import cv2
import numpy as np
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, RTCConfiguration, RTCIceServer
import av
import threading
from collections import deque
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WebRTCClient:
    def __init__(self, signaling_server='ws://localhost:8765', room_id='default'):
        self.signaling_server = signaling_server
        self.room_id = room_id
        self.peer_id = f"client_{uuid.uuid4().hex[:8]}"
        self.websocket = None
        self.peer_connection = None
        self.host_id = None
        
        # WebRTC configuration with STUN servers
        self.ice_servers = [
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        ]
        
        # Video display
        self.frame_queue = deque(maxlen=3)  # Small buffer for low latency
        self.display_thread = None
        self.running = False
        self.stats = {
            'frames_received': 0,
            'frames_displayed': 0,
            'last_fps_check': time.time(),
            'fps': 0
        }
        
    async def connect_signaling(self):
        """Connect to signaling server"""
        try:
            self.websocket = await websockets.connect(self.signaling_server)
            logger.info(f"Connected to signaling server: {self.signaling_server}")
            
            # Register as client
            await self.websocket.send(json.dumps({
                'type': 'register',
                'peer_type': 'client',
                'peer_id': self.peer_id,
                'room_id': self.room_id
            }))
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to signaling server: {e}")
            return False
    
    async def create_peer_connection(self):
        """Create WebRTC peer connection"""
        self.peer_connection = RTCPeerConnection(configuration=RTCConfiguration(iceServers=self.ice_servers))
        
        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state: {self.peer_connection.connectionState}")
        
        @self.peer_connection.on("track")
        def on_track(track):
            logger.info(f"Received track: {track.kind}")
            if track.kind == "video":
                # Start receiving video frames
                asyncio.create_task(self.receive_video_frames(track))
        
        @self.peer_connection.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate and self.host_id:
                await self.websocket.send(json.dumps({
                    'type': 'ice_candidate',
                    'sender': self.peer_id,
                    'target': self.host_id,
                    'candidate': {
                        'candidate': candidate.candidate,
                        'sdpMid': candidate.sdpMid,
                        'sdpMLineIndex': candidate.sdpMLineIndex
                    }
                }))
    
    async def receive_video_frames(self, track):
        """Receive and queue video frames"""
        logger.info("Started receiving video frames")
        self.running = True
        
        # Start display thread
        self.display_thread = threading.Thread(target=self.display_frames)
        self.display_thread.daemon = True
        self.display_thread.start()
        
        try:
            while True:
                frame = await track.recv()
                
                # Convert av.VideoFrame to numpy array
                img = frame.to_ndarray(format='rgb24')
                
                # Convert RGB to BGR for OpenCV
                img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                
                # Add to queue
                self.frame_queue.append(img_bgr)
                self.stats['frames_received'] += 1
                
        except Exception as e:
            logger.error(f"Error receiving frames: {e}")
        finally:
            self.running = False
    
    def display_frames(self):
        """Display frames using OpenCV (runs in separate thread)"""
        cv2.namedWindow('WebRTC Remote Screen', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('WebRTC Remote Screen', 1280, 720)
        
        while self.running:
            if self.frame_queue:
                frame = self.frame_queue.popleft()
                
                # Display frame
                cv2.imshow('WebRTC Remote Screen', frame)
                self.stats['frames_displayed'] += 1
                
                # Update FPS counter
                current_time = time.time()
                if current_time - self.stats['last_fps_check'] >= 1.0:
                    self.stats['fps'] = self.stats['frames_displayed']
                    self.stats['frames_displayed'] = 0
                    self.stats['last_fps_check'] = current_time
                    
                    # Update window title
                    title = f"WebRTC Remote Screen - {self.stats['fps']} FPS"
                    cv2.setWindowTitle('WebRTC Remote Screen', title)
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC
                    self.running = False
                    break
                elif key == ord('f'):  # 'f' for fullscreen
                    cv2.setWindowProperty('WebRTC Remote Screen', 
                                        cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                elif key == ord('w'):  # 'w' for windowed
                    cv2.setWindowProperty('WebRTC Remote Screen', 
                                        cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            else:
                time.sleep(0.001)  # Small delay when no frames
        
        cv2.destroyAllWindows()
        logger.info("Display stopped")
    
    async def handle_offer(self, message):
        """Handle WebRTC offer from host"""
        offer = message['offer']
        logger.info("Received offer from host")
        
        # Set remote description
        await self.peer_connection.setRemoteDescription(RTCSessionDescription(
            sdp=offer['sdp'],
            type=offer['type']
        ))
        
        # Create answer
        answer = await self.peer_connection.createAnswer()
        await self.peer_connection.setLocalDescription(answer)
        
        # Send answer to host
        await self.websocket.send(json.dumps({
            'type': 'answer',
            'sender': self.peer_id,
            'target': self.host_id,
            'answer': {
                'sdp': self.peer_connection.localDescription.sdp,
                'type': self.peer_connection.localDescription.type
            }
        }))
        
        logger.info("Sent answer to host")
    

    
    async def handle_ice_candidate(self, message):
        """Handle ICE candidate from host"""
        candidate_data = message['candidate']
        
        if self.peer_connection:
            candidate = av.RTCIceCandidate(
                candidate=candidate_data['candidate'],
                sdpMid=candidate_data['sdpMid'],
                sdpMLineIndex=candidate_data['sdpMLineIndex']
            )
            await self.peer_connection.addIceCandidate(candidate)
            logger.info("Added ICE candidate from host")
    
    async def handle_signaling_messages(self):
        """Handle incoming signaling messages"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'registered':
                        logger.info(f"Registered as client: {data['peer_id']}")
                    
                    elif msg_type == 'host_available':
                        host_id = data.get('host_id')
                        logger.info(f"Host available: {host_id}")
                        # Set up peer connection and wait for offer from host
                        self.host_id = host_id
                        await self.create_peer_connection()
                        
                        # Send ready signal to host
                        await self.websocket.send(json.dumps({
                            'type': 'client_ready',
                            'sender': self.peer_id,
                            'target': host_id
                        }))
                    
                    elif msg_type == 'offer':
                        await self.handle_offer(data)
                    
                    elif msg_type == 'ice_candidate':
                        await self.handle_ice_candidate(data)
                    
                    else:
                        logger.info(f"Received: {msg_type}")
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info("Signaling connection closed")
        except Exception as e:
            logger.error(f"Signaling error: {e}")
    
    async def start_client(self):
        """Start the WebRTC client"""
        logger.info(f"Starting WebRTC client: {self.peer_id}")
        logger.info(f"Room: {self.room_id}")
        logger.info("Controls: Q/ESC=Quit, F=Fullscreen, W=Windowed")
        
        if not await self.connect_signaling():
            return
        
        try:
            await self.handle_signaling_messages()
        except KeyboardInterrupt:
            logger.info("Client stopped by user")
        finally:
            # Clean up
            self.running = False
            if self.peer_connection:
                await self.peer_connection.close()
            if self.websocket:
                await self.websocket.close()
            logger.info("Client stopped")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='WebRTC Screen Client')
    parser.add_argument('--signaling', default='ws://localhost:8765', 
                       help='Signaling server URL')
    parser.add_argument('--room', default='default', 
                       help='Room ID')
    
    args = parser.parse_args()
    
    client = WebRTCClient(args.signaling, args.room)
    
    try:
        asyncio.run(client.start_client())
    except KeyboardInterrupt:
        logger.info("Client stopped")