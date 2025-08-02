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
        self.frame_count = 0
        self._started = False
        
        # Get monitor info
        with mss() as sct:
            self.monitor = sct.monitors[1]  # Primary monitor
        
        logger.info(f"Created ScreenStreamTrack - Resolution: {self.monitor['width']}x{self.monitor['height']}")
    
    def start(self):
        """Start the track"""
        self._started = True
        logger.info("ScreenStreamTrack started")
        
    async def recv(self):
        """Capture and return video frame"""
        if self.frame_count == 0:
            logger.info("ScreenStreamTrack.recv() called for the first time - track is working!")
        
        try:
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
                
                self.frame_count += 1
                if self.frame_count <= 5 or self.frame_count % 60 == 0:
                    logger.info(f"ScreenStreamTrack generated frame #{self.frame_count}")
                
                return frame
        except Exception as e:
            logger.error(f"Error in ScreenStreamTrack.recv(): {e}")
            raise

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
        
        # Create a fresh screen stream track for each connection
        # This ensures proper streaming for reconnections
        screen_track = ScreenStreamTrack(fps=30, quality=85)
        
        # Add track with explicit transceiver to ensure proper setup
        transceiver = pc.addTransceiver(screen_track, direction="sendonly")
        logger.info(f"Added fresh screen track for client {client_id} with transceiver direction: {transceiver.direction}")
        
        # Start the track
        screen_track.start()
        
        # Verify the track was added
        transceivers = pc.getTransceivers()
        logger.info(f"Peer connection for {client_id} has {len(transceivers)} transceivers")
        
        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            state = pc.connectionState
            logger.info(f"Connection state for {client_id}: {state}")
            
            if state == "connected":
                logger.info(f"🎉 P2P connection established with {client_id} - signaling server no longer needed for this connection")
            elif state in ["closed", "failed", "disconnected"]:
                logger.info(f"Cleaning up connection for {client_id}")
                if client_id in self.peer_connections:
                    try:
                        await self.peer_connections[client_id].close()
                    except:
                        pass
                    del self.peer_connections[client_id]
        
        @pc.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate:
                try:
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
                except Exception as e:
                    logger.error(f"Error sending ICE candidate to {client_id}: {e}")
        
        @pc.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            logger.info(f"ICE connection state for {client_id}: {pc.iceConnectionState}")
            if pc.iceConnectionState in ["failed", "disconnected"]:
                logger.warning(f"ICE connection failed/disconnected for {client_id}")
                # The connection state handler will clean up
            elif pc.iceConnectionState == "connected":
                logger.info(f"ICE connection established for {client_id} - video should start streaming")
        
        @pc.on("track")
        def on_track(track):
            logger.info(f"Host received track from {client_id}: {track.kind}")
        
        # Add datachannel state monitoring
        @pc.on("datachannel")
        def on_datachannel(channel):
            logger.info(f"Host received datachannel from {client_id}: {channel.label}")
        
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
        
        # Log SDP for debugging
        logger.info(f"Created offer for {client_id} with {len(pc.getTransceivers())} transceivers")
        for i, transceiver in enumerate(pc.getTransceivers()):
            logger.info(f"Transceiver {i}: {transceiver.kind} - direction: {transceiver.direction}")
        
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
    
    async def handle_client_disconnected(self, message):
        """Handle client disconnection notification"""
        client_id = message['client_id']
        logger.info(f"Client {client_id} disconnected, cleaning up connection")
        
        if client_id in self.peer_connections:
            try:
                await self.peer_connections[client_id].close()
            except Exception as e:
                logger.error(f"Error closing connection for {client_id}: {e}")
            del self.peer_connections[client_id]
            logger.info(f"Cleaned up connection for {client_id}")
    
    async def run_p2p_mode(self):
        """Continue running in P2P mode after signaling server disconnects"""
        logger.info("🎯 Host running in P2P mode - signaling server no longer needed")
        
        try:
            while self.peer_connections:
                await asyncio.sleep(5)
                
                # Show status of active connections
                active_count = len(self.peer_connections)
                logger.info(f"📺 Host maintaining {active_count} P2P connection(s)")
                
                # Clean up any closed connections
                closed_connections = []
                for client_id, pc in self.peer_connections.items():
                    if pc.connectionState in ["closed", "failed", "disconnected"]:
                        closed_connections.append(client_id)
                
                for client_id in closed_connections:
                    logger.info(f"Removing closed connection: {client_id}")
                    if client_id in self.peer_connections:
                        del self.peer_connections[client_id]
            
            logger.info("All P2P connections closed, shutting down host")
            
        except KeyboardInterrupt:
            logger.info("P2P mode stopped by user")
    
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
                    
                    elif msg_type == 'client_disconnected':
                        await self.handle_client_disconnected(data)
                    
                    else:
                        logger.info(f"Received: {msg_type}")
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Signaling connection closed")
            # Check if we have active P2P connections
            active_connections = len(self.peer_connections)
            if active_connections > 0:
                logger.info(f"📺 Continuing with {active_connections} active P2P connection(s)")
                # Keep the host running to maintain P2P connections
                await self.run_p2p_mode()
            else:
                logger.info("No active P2P connections, shutting down")
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
            # Create a copy of the values to avoid "dictionary changed size during iteration" error
            peer_connections_copy = list(self.peer_connections.values())
            for pc in peer_connections_copy:
                try:
                    await pc.close()
                except Exception as e:
                    logger.error(f"Error closing peer connection: {e}")
            
            if self.websocket:
                try:
                    await self.websocket.close()
                except Exception as e:
                    logger.error(f"Error closing websocket: {e}")
            
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