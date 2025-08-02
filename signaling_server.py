#!/usr/bin/env python3
"""
WebRTC Signaling Server
Handles peer discovery and WebRTC signaling for screen streaming
"""

import asyncio
import json
import logging
import websockets
from websockets.server import serve
from typing import Dict, Set

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SignalingServer:
    def __init__(self):
        self.hosts: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.clients: Dict[str, websockets.WebSocketServerProtocol] = {}
        self.rooms: Dict[str, Dict] = {}
    
    async def register_peer(self, websocket, message):
        """Register a peer as host or client"""
        peer_type = message.get('peer_type')
        peer_id = message.get('peer_id')
        room_id = message.get('room_id', 'default')
        
        if peer_type == 'host':
            self.hosts[peer_id] = websocket
            logger.info(f"Host {peer_id} registered in room {room_id}")
        elif peer_type == 'client':
            self.clients[peer_id] = websocket
            logger.info(f"Client {peer_id} registered in room {room_id}")
        
        # Initialize room if it doesn't exist
        if room_id not in self.rooms:
            self.rooms[room_id] = {'host': None, 'clients': set()}
        
        # Add peer to room
        if peer_type == 'host':
            self.rooms[room_id]['host'] = peer_id
        else:
            self.rooms[room_id]['clients'].add(peer_id)
        
        # Send registration confirmation
        await websocket.send(json.dumps({
            'type': 'registered',
            'peer_id': peer_id,
            'room_id': room_id
        }))
        
        # Notify about available peers
        await self.notify_peers(room_id)
    
    async def notify_peers(self, room_id):
        """Notify peers in a room about available connections"""
        if room_id not in self.rooms:
            return
        
        room = self.rooms[room_id]
        host_id = room['host']
        client_ids = list(room['clients'])
        
        logger.info(f"Notifying peers in room {room_id}: host={host_id}, clients={client_ids}")
        
        # Notify clients about available host
        if host_id and host_id in self.hosts:
            for client_id in client_ids:
                if client_id in self.clients:
                    logger.info(f"Notifying client {client_id} about host {host_id}")
                    await self.clients[client_id].send(json.dumps({
                        'type': 'host_available',
                        'host_id': host_id,
                        'room_id': room_id
                    }))
        
        # Notify host about available clients
        if host_id and host_id in self.hosts and client_ids:
            logger.info(f"Notifying host {host_id} about clients {client_ids}")
            await self.hosts[host_id].send(json.dumps({
                'type': 'clients_available',
                'client_ids': client_ids,
                'room_id': room_id
            }))
    
    async def relay_message(self, websocket, message):
        """Relay WebRTC signaling messages between peers"""
        target_id = message.get('target')
        sender_id = message.get('sender')
        
        # Find target websocket
        target_ws = None
        if target_id in self.hosts:
            target_ws = self.hosts[target_id]
        elif target_id in self.clients:
            target_ws = self.clients[target_id]
        
        if target_ws:
            # Forward the message
            await target_ws.send(json.dumps(message))
            logger.info(f"Relayed {message.get('type')} from {sender_id} to {target_id}")
        else:
            logger.warning(f"Target {target_id} not found for message from {sender_id}")
    
    async def handle_client(self, websocket, path):
        """Handle WebSocket client connections"""
        peer_id = None
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'register':
                        peer_id = data.get('peer_id')
                        await self.register_peer(websocket, data)
                    
                    elif msg_type in ['offer', 'answer', 'ice_candidate', 'client_ready']:
                        await self.relay_message(websocket, data)
                    
                    else:
                        logger.warning(f"Unknown message type: {msg_type}")
                
                except json.JSONDecodeError:
                    logger.error("Invalid JSON received")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")
        
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Peer {peer_id} disconnected")
        except Exception as e:
            logger.error(f"Connection error: {e}")
        finally:
            # Clean up on disconnect
            if peer_id:
                if peer_id in self.hosts:
                    del self.hosts[peer_id]
                if peer_id in self.clients:
                    del self.clients[peer_id]
                
                # Remove from rooms
                for room_id, room in self.rooms.items():
                    if room['host'] == peer_id:
                        room['host'] = None
                    room['clients'].discard(peer_id)
    
    async def start_server(self, host='localhost', port=8765):
        """Start the signaling server"""
        logger.info(f"Starting signaling server on {host}:{port}")
        
        async with serve(self.handle_client, host, port):
            logger.info("Signaling server started. Waiting for connections...")
            await asyncio.Future()  # Run forever

if __name__ == "__main__":
    server = SignalingServer()
    
    try:
        asyncio.run(server.start_server('0.0.0.0', 8765))
    except KeyboardInterrupt:
        logger.info("Signaling server stopped")