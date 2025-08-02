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
        
        # P2P state tracking
        self.webrtc_connected = False
        self.signaling_needed = True
        
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
    
    async def close_signaling_connection(self):
        """Close signaling connection after WebRTC is established"""
        if self.websocket and not self.websocket.closed:
            logger.info("🔌 Closing signaling connection - now running purely P2P")
            self.signaling_needed = False
            try:
                await self.websocket.close()
            except:
                pass
            self.websocket = None
    
    async def create_peer_connection(self):
        """Create WebRTC peer connection"""
        # Close existing connection if any
        if self.peer_connection:
            try:
                await self.peer_connection.close()
            except:
                pass
        
        self.peer_connection = RTCPeerConnection(configuration=RTCConfiguration(iceServers=self.ice_servers))
        
        @self.peer_connection.on("connectionstatechange")
        async def on_connectionstatechange():
            state = self.peer_connection.connectionState
            logger.info(f"WebRTC connection state: {state}")
            
            if state == "connected":
                self.webrtc_connected = True
                self.signaling_needed = False  # Mark that we no longer need signaling
                logger.info("🎉 WebRTC P2P connection established! Now running independently of signaling server.")
                
            elif state in ["closed", "failed", "disconnected"]:
                logger.info("WebRTC connection lost")
                self.webrtc_connected = False
                self.running = False
        
        @self.peer_connection.on("track")
        def on_track(track):
            logger.info(f"Received track: {track.kind} (readyState: {track.readyState})")
            if track.kind == "video":
                logger.info("Starting video frame reception")
                # Start receiving video frames
                asyncio.create_task(self.receive_video_frames(track))
        
        @self.peer_connection.on("icecandidate")
        async def on_icecandidate(candidate):
            if candidate and self.host_id and self.signaling_needed:
                try:
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
                except Exception as e:
                    logger.error(f"Error sending ICE candidate: {e}")
        
        @self.peer_connection.on("icegatheringstatechange")
        async def on_icegatheringstatechange():
            logger.info(f"ICE gathering state: {self.peer_connection.iceGatheringState}")
        
        @self.peer_connection.on("iceconnectionstatechange")
        async def on_iceconnectionstatechange():
            ice_state = self.peer_connection.iceConnectionState
            logger.info(f"ICE connection state: {ice_state}")
            
            if ice_state == "connected":
                logger.info("✅ ICE connection established - P2P media flow active")
            elif ice_state == "failed":
                logger.error("❌ ICE connection failed")
                self.running = False
            elif ice_state == "disconnected":
                logger.warning("ICE connection disconnected")
    
    async def receive_video_frames(self, track):
        """Receive and queue video frames"""
        logger.info(f"Started receiving video frames from track (readyState: {track.readyState})")
        
        # Only start if not already running
        if not self.running:
            self.running = True
            
            # Start display thread if not already running
            if not self.display_thread or not self.display_thread.is_alive():
                self.display_thread = threading.Thread(target=self.display_frames)
                self.display_thread.daemon = True
                self.display_thread.start()
                logger.info("Started display thread")
        
        frame_count = 0
        try:
            # Keep receiving frames as long as we're running
            # Don't check webrtc_connected here as it might not be set yet when track starts
            while self.running:
                frame = await track.recv()
                frame_count += 1
                
                if frame_count % 30 == 0:  # Log every 30 frames
                    logger.info(f"Received {frame_count} frames")
                
                # Convert av.VideoFrame to numpy array
                img = frame.to_ndarray(format='rgb24')
                
                # Convert RGB to BGR for OpenCV
                img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
                
                # Add to queue
                self.frame_queue.append(img_bgr)
                self.stats['frames_received'] += 1
                
        except Exception as e:
            logger.error(f"Error receiving frames after {frame_count} frames: {e}")
        finally:
            logger.info(f"Stopped receiving frames (total: {frame_count})")
            self.running = False
    
    def display_frames(self):
        """Display frames using OpenCV (runs in separate thread)"""
        logger.info("Display thread started")
        cv2.namedWindow('P2P WebRTC Stream', cv2.WINDOW_NORMAL)
        cv2.resizeWindow('P2P WebRTC Stream', 1280, 720)
        
        frames_displayed_total = 0
        last_frame_time = time.time()
        
        while self.running:
            if self.frame_queue:
                frame = self.frame_queue.popleft()
                frames_displayed_total += 1
                
                # Display frame
                cv2.imshow('P2P WebRTC Stream', frame)
                self.stats['frames_displayed'] += 1
                
                # Log first few frames and periodically
                if frames_displayed_total <= 5 or frames_displayed_total % 60 == 0:
                    logger.info(f"Displayed frame #{frames_displayed_total}")
                
                last_frame_time = time.time()
                
                # Update FPS counter
                current_time = time.time()
                if current_time - self.stats['last_fps_check'] >= 1.0:
                    self.stats['fps'] = self.stats['frames_displayed']
                    self.stats['frames_displayed'] = 0
                    self.stats['last_fps_check'] = current_time
                    
                    # Update window title with P2P status
                    p2p_status = "P2P" if self.webrtc_connected and not self.signaling_needed else "Signaling"
                    title = f"WebRTC Stream ({p2p_status}) - {self.stats['fps']} FPS"
                    cv2.setWindowTitle('P2P WebRTC Stream', title)
                
                # Handle key presses
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q') or key == 27:  # 'q' or ESC
                    self.running = False
                    break
                elif key == ord('f'):  # 'f' for fullscreen
                    cv2.setWindowProperty('P2P WebRTC Stream', 
                                        cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
                elif key == ord('w'):  # 'w' for windowed
                    cv2.setWindowProperty('P2P WebRTC Stream', 
                                        cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
            else:
                # Check if we haven't received frames for too long
                current_time = time.time()
                if current_time - last_frame_time > 5.0 and frames_displayed_total > 0:
                    logger.warning("No frames received for 5 seconds")
                    last_frame_time = current_time
                
                time.sleep(0.001)  # Small delay when no frames
        
        cv2.destroyAllWindows()
        logger.info(f"Display stopped (total frames displayed: {frames_displayed_total})")
    
    async def handle_offer(self, message):
        """Handle WebRTC offer from host"""
        offer = message['offer']
        logger.info("Received offer from host")
        
        # Set remote description
        await self.peer_connection.setRemoteDescription(RTCSessionDescription(
            sdp=offer['sdp'],
            type=offer['type']
        ))
        
        # Log transceivers before creating answer
        logger.info(f"Client has {len(self.peer_connection.getTransceivers())} transceivers after setting remote description")
        for i, transceiver in enumerate(self.peer_connection.getTransceivers()):
            logger.info(f"Transceiver {i}: {transceiver.kind} - direction: {transceiver.direction}")
        
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
        """Handle incoming signaling messages until WebRTC is established"""
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
                        
                        # Reset client state for new connection
                        self.running = False
                        self.frame_queue.clear()
                        
                        # Set up peer connection and wait for offer from host
                        self.host_id = host_id
                        await self.create_peer_connection()
                        
                        # Send ready signal to host
                        await self.websocket.send(json.dumps({
                            'type': 'client_ready',
                            'sender': self.peer_id,
                            'target': host_id
                        }))
                        logger.info(f"Sent ready signal to host {host_id}")
                    
                    elif msg_type == 'offer':
                        await self.handle_offer(data)
                        # Start a timeout to detect if streaming doesn't start
                        asyncio.create_task(self.check_streaming_timeout())
                    
                    elif msg_type == 'ice_candidate':
                        await self.handle_ice_candidate(data)
                    
                    elif msg_type == 'host_disconnected':
                        logger.info("Host disconnected, waiting for reconnection...")
                        # Clean up current connection
                        if self.peer_connection:
                            await self.peer_connection.close()
                            self.peer_connection = None
                        self.host_id = None
                        self.running = False
                    
                    else:
                        logger.info(f"Received: {msg_type}")
                    
                    # Break out of signaling loop if WebRTC is connected
                    if self.webrtc_connected:
                        logger.info("WebRTC connected, transitioning to P2P mode")
                        break
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            if not self.webrtc_connected:
                logger.error("Signaling connection closed before WebRTC was established")
                return False
            else:
                logger.info("Signaling connection closed - continuing with P2P connection")
                return True
        except Exception as e:
            logger.error(f"Signaling error: {e}")
            return False
        
        return self.webrtc_connected
    
    async def start_client(self):
        """Start the WebRTC client with P2P capability"""
        logger.info(f"🚀 Starting WebRTC client: {self.peer_id}")
        logger.info(f"Room: {self.room_id}")
        logger.info("Controls: Q/ESC=Quit, F=Fullscreen, W=Windowed")
        
        # Step 1: Connect to signaling server and establish WebRTC
        if not await self.connect_signaling():
            return
        
        try:
            # Handle signaling messages until WebRTC is established
            await self.handle_signaling_messages()
            
            # Step 2: If WebRTC is connected, continue P2P session
            if self.webrtc_connected:
                logger.info("🎯 WebRTC connection established - now running independently!")
                await self.run_p2p_session()
            else:
                logger.error("Failed to establish WebRTC connection")
                
        except KeyboardInterrupt:
            logger.info("Client stopped by user")
        finally:
            await self.cleanup()
    
    async def run_p2p_session(self):
        """Run P2P session independently of signaling server"""
        logger.info("🎯 Starting P2P session - signaling server can now be terminated!")
        
        # Create a background task to monitor signaling connection loss
        signaling_monitor_task = asyncio.create_task(self.monitor_signaling_connection())
        
        try:
            frame_check_counter = 0
            while self.webrtc_connected:
                await asyncio.sleep(1)
                frame_check_counter += 1
                
                # Show status every 5 seconds
                if frame_check_counter % 5 == 0:
                    if self.stats['frames_received'] > 0:
                        logger.info(f"📺 P2P streaming active - {self.stats['frames_received']} frames received in last 5s")
                        self.stats['frames_received'] = 0  # Reset counter
                    else:
                        logger.info("📺 P2P connection active (waiting for frames)")
                
                # Check if we're still running
                if not self.running:
                    logger.info("Display stopped, ending P2P session")
                    break
        
        except KeyboardInterrupt:
            logger.info("P2P session stopped by user")
        finally:
            signaling_monitor_task.cancel()
    
    async def monitor_signaling_connection(self):
        """Monitor signaling connection in background during P2P session"""
        try:
            if self.websocket and not self.websocket.closed:
                # Continue listening for any remaining signaling messages
                # but don't let connection loss stop the P2P session
                async for message in self.websocket:
                    try:
                        data = json.loads(message)
                        msg_type = data.get('type')
                        logger.info(f"Received signaling message during P2P: {msg_type}")
                        
                        # Handle any important messages like host disconnection
                        if msg_type == 'host_disconnected':
                            logger.warning("Host disconnected - P2P connection may be lost soon")
                            
                    except json.JSONDecodeError:
                        pass
                    except Exception as e:
                        logger.debug(f"Error in signaling monitor: {e}")
        except websockets.exceptions.ConnectionClosed:
            logger.info("🔌 Signaling server disconnected - P2P session continues independently!")
        except asyncio.CancelledError:
            logger.debug("Signaling monitor cancelled")
        except Exception as e:
            logger.debug(f"Signaling monitor error: {e}")
    
    async def cleanup(self):
        """Clean up resources"""
        logger.info("Cleaning up client resources")
        self.running = False
        
        # Close peer connection
        if self.peer_connection:
            try:
                await self.peer_connection.close()
            except Exception as e:
                logger.error(f"Error closing peer connection: {e}")
            self.peer_connection = None
        
        # Close websocket
        if self.websocket:
            try:
                await self.websocket.close()
            except Exception as e:
                logger.error(f"Error closing websocket: {e}")
            self.websocket = None
        
        # Wait for display thread to finish
        if self.display_thread and self.display_thread.is_alive():
            self.display_thread.join(timeout=2.0)
        
        logger.info("Client stopped")
    
    async def check_streaming_timeout(self):
        """Check if streaming starts within a reasonable time"""
        await asyncio.sleep(10)  # Wait 10 seconds
        
        if self.stats['frames_received'] == 0:
            logger.error("No frames received within 10 seconds - connection may have failed")
            logger.info("Try restarting the client if the screen remains blank")

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