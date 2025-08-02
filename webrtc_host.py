#!/usr/bin/env python3
"""
WebRTC Screen Host - Streams screen using WebRTC
Supports NAT traversal with STUN/TURN servers
"""

import asyncio
import json
import logging
import uuid
import cv2
import numpy as np
from mss import mss
from PIL import Image
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription, VideoStreamTrack, RTCConfiguration, RTCIceServer
from aiortc.contrib.media import MediaPlayer
import av
from fractions import Fraction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ScreenStreamTrack(VideoStreamTrack):
    """Custom video track that captures screen content"""
    
    def __init__(self, fps=30, quality=85):
        super().__init__()
        self.fps = fps
        self.quality = quality
        self.frame_time = 1.0 / fps
        
        # Get monitor info
        with mss() as sct:
            self.monitor = sct.monitors[1]  # Primary monitor
        
        logger.info(f"Screen resolution: {self.monitor['width']}x{self.monitor['height']}")
        
    async def recv(self):
        """Capture and return video frame"""
        pts, time_base = await self.next_timestamp()
        
        # Capture screen
        with mss() as sct:
            screenshot = sct.grab(self.monitor)
            
            # Convert to PIL Image
            img = Image.frombytes('RGB', screenshot.size, screenshot.bgra, 'raw', 'BGRX')
            
            # Convert to numpy array
            img_array = np.array(img)
            
            # Convert BGR to RGB (OpenCV uses BGR, but we need RGB for WebRTC)
            img_rgb = cv2.cvtColor(img_array, cv2.COLOR_BGR2RGB)
            
            # Create av.VideoFrame
            frame = av.VideoFrame.from_ndarray(img_rgb, format='rgb24')
            frame.pts = pts
            frame.time_base = time_base
            
            return frame

class WebRTCHost:
    def __init__(self, signaling_server='ws://localhost:8765', room_id='default'):
        self.signaling_server = signaling_server
        self.room_id = room_id
        self.peer_id = f"host_{uuid.uuid4().hex[:8]}"
        self.websocket = None
        self.peer_connections = {}
        
        # WebRTC configuration with STUN servers
        self.ice_servers = [
            RTCIceServer(urls=["stun:stun.l.google.com:19302"]),
            RTCIceServer(urls=["stun:stun1.l.google.com:19302"]),
        ]
        
        self.screen_track = None
        
    async def connect_signaling(self):
        """Connect to signaling server"""
        try:
            self.websocket = await websockets.connect(self.signaling_server)
            logger.info(f"Connected to signaling server: {self.signaling_server}")
            
            # Register as host
            await self.websocket.send(json.dumps({
                'type': 'register',
                'peer_type': 'host',
                'peer_id': self.peer_id,
                'room_id': self.room_id
            }))
            
            return True
        except Exception as e:
            logger.error(f"Failed to connect to signaling server: {e}")
            return False
    
    async def create_peer_connection(self, client_id):
        """Create WebRTC peer connection for a client"""
        pc = RTCPeerConnection(configuration=RTCConfiguration(iceServers=self.ice_servers))
        self.peer_connections[client_id] = pc
        
        # Add screen stream track
        if not self.screen_track:
            self.screen_track = ScreenStreamTrack(fps=30, quality=85)
        
        pc.addTrack(self.screen_track)
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            logger.info(f"Connection state for {client_id}: {pc.connectionState}")
            if pc.connectionState == "closed":
                if client_id in self.peer_connections:
                    del self.peer_connections[client_id]
        
        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                await self.websocket.send(json.dumps({
                    'type': 'ice_candidate',
                    'sender': self.peer_id,
                    'target': client_id,
                    'candidate': {
                        'candidate': candidate.candidate,
                        'sdpMid': candidate.sdpMid,
                        'sdpMLineIndex': candidate.sdpMLineIndex
                    }
                }))
        
        return pc
    
    async def handle_client_ready(self, message):
        """Handle client ready signal and create offer"""
        client_id = message['sender']
        logger.info(f"Client {client_id} is ready, creating offer")
        
        # Create peer connection
        pc = await self.create_peer_connection(client_id)
        
        # Create offer
        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        
        # Send offer
        await self.websocket.send(json.dumps({
            'type': 'offer',
            'sender': self.peer_id,
            'target': client_id,
            'offer': {
                'sdp': pc.localDescription.sdp,
                'type': pc.localDescription.type
            }
        }))
        
        logger.info(f"Sent offer to {client_id}")
    
    async def handle_answer(self, message):
        """Handle WebRTC answer from client"""
        client_id = message['sender']
        answer = message['answer']
        
        logger.info(f"Received answer from {client_id}")
        
        if client_id in self.peer_connections:
            pc = self.peer_connections[client_id]
            await pc.setRemoteDescription(RTCSessionDescription(
                sdp=answer['sdp'],
                type=answer['type']
            ))
            logger.info(f"WebRTC connection established with {client_id}")
    
    async def handle_ice_candidate(self, message):
        """Handle ICE candidate from client"""
        client_id = message['sender']
        candidate_data = message['candidate']
        
        if client_id in self.peer_connections:
            pc = self.peer_connections[client_id]
            candidate = av.RTCIceCandidate(
                candidate=candidate_data['candidate'],
                sdpMid=candidate_data['sdpMid'],
                sdpMLineIndex=candidate_data['sdpMLineIndex']
            )
            await pc.addIceCandidate(candidate)
            logger.info(f"Added ICE candidate from {client_id}")
    
    async def handle_signaling_messages(self):
        """Handle incoming signaling messages"""
        try:
            async for message in self.websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'registered':
                        logger.info(f"Registered as host: {data['peer_id']}")
                    
                    elif msg_type == 'clients_available':
                        client_ids = data.get('client_ids', [])
                        logger.info(f"Available clients: {client_ids}")
                    
                    elif msg_type == 'client_ready':
                        await self.handle_client_ready(data)
                    
                    elif msg_type == 'answer':
                        await self.handle_answer(data)
                    
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
    
    async def start_host(self):
        """Start the WebRTC host"""
        logger.info(f"Starting WebRTC host: {self.peer_id}")
        logger.info(f"Room: {self.room_id}")
        
        if not await self.connect_signaling():
            return
        
        try:
            await self.handle_signaling_messages()
        except KeyboardInterrupt:
            logger.info("Host stopped by user")
        finally:
            # Clean up
            for pc in self.peer_connections.values():
                await pc.close()
            if self.websocket:
                await self.websocket.close()
            logger.info("Host stopped")

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description='WebRTC Screen Host')
    parser.add_argument('--signaling', default='ws://localhost:8765', 
                       help='Signaling server URL')
    parser.add_argument('--room', default='default', 
                       help='Room ID')
    
    args = parser.parse_args()
    
    host = WebRTCHost(args.signaling, args.room)
    
    try:
        asyncio.run(host.start_host())
    except KeyboardInterrupt:
        logger.info("Host stopped")