"""
Twitch EventSub WebSocket client for channel points.
Handles connection to Twitch EventSub WebSocket and subscriptions.
"""
import asyncio
import websockets
import json
import logging
from typing import Callable, Dict, List
import aiohttp

logger = logging.getLogger(__name__)

class EventSubClient:
    """
    EventSub WebSocket client for local channel points support.
    """
    
    EVENTSUB_WS_URL = "wss://eventsub.wss.twitch.tv/ws"
    
    def __init__(self, client_id: str, access_token: str):
        self.client_id = client_id
        self.access_token = access_token
        self.websocket = None
        self.session_id = None
        self.running = False
        self.subscriptions = []
        self.callbacks: Dict[str, Callable] = {}

    async def connect(self):
        """Connect to EventSub WebSocket."""
        try:
            print("[EventSub] Connecting...")
            self.websocket = await websockets.connect(self.EVENTSUB_WS_URL)
            self.running = True
            print("[EventSub] Connected!")
            
            # Start listening
            asyncio.create_task(self.listen())
            
        except Exception as e:
            print(f"[EventSub] Connection failed: {e}")
            raise

    async def listen(self):
        """Listen for WebSocket messages with auto-reconnect."""
        reconnect_attempts = 0
        max_reconnect_attempts = 5
        
        while self.running:
            try:
                async for message in self.websocket:
                    await self.handle_message(message)
                    reconnect_attempts = 0  # Reset on successful message
            except Exception as e:
                print(f"[EventSub] Error in listener: {e}")
                
                if not self.running:
                    break
                
                reconnect_attempts += 1
                if reconnect_attempts > max_reconnect_attempts:
                    print(f"[EventSub] Max reconnection attempts reached. Giving up.")
                    self.running = False
                    break
                
                # Exponential backoff: 2, 4, 8, 16, 32 seconds
                delay = min(2 ** reconnect_attempts, 32)
                print(f"[EventSub] Reconnecting in {delay}s (attempt {reconnect_attempts}/{max_reconnect_attempts})...")
                await asyncio.sleep(delay)
                
                try:
                    await self.fresh_connect()
                except Exception as reconnect_error:
                    print(f"[EventSub] Reconnection failed: {reconnect_error}")
    
    async def fresh_connect(self):
        """Reconnect to EventSub from scratch (new session)."""
        if self.websocket:
            try:
                await self.websocket.close()
            except:
                pass
        
        print("[EventSub] Reconnecting...")
        self.websocket = await websockets.connect(self.EVENTSUB_WS_URL)
        self.session_id = None  # Will be set by session_welcome
        print("[EventSub] Reconnected!")

    async def handle_message(self, message: str):
        try:
            data = json.loads(message)
            msg_type = data.get('metadata', {}).get('message_type')
            
            if msg_type == 'session_welcome':
                self.session_id = data['payload']['session']['id']
                print(f"[EventSub] Session ID: {self.session_id}")
                await self.create_subscriptions()
                
            elif msg_type == 'notification':
                await self.handle_notification(data)
                
            elif msg_type == 'session_reconnect':
                reconnect_url = data['payload']['session']['reconnect_url']
                await self.reconnect(reconnect_url)
                
        except Exception as e:
            print(f"[EventSub] Error handling message: {e}")

    async def handle_notification(self, data: dict):
        subscription_type = data.get('metadata', {}).get('subscription_type')
        event_data = data.get('payload', {}).get('event', {})
        
        if subscription_type in self.callbacks:
            try:
                await self.callbacks[subscription_type](event_data)
            except Exception as e:
                print(f"[EventSub] Callback error: {e}")

    def subscribe_channel_points(self, broadcaster_id: str, callback: Callable):
        """Subscribe to channel points redemptions."""
        sub_type = "channel.channel_points_custom_reward_redemption.add"
        self.callbacks[sub_type] = callback
        
        self.subscriptions.append({
            "type": sub_type,
            "broadcaster_id": broadcaster_id
        })

    async def create_subscriptions(self):
        """Create subscriptions via Twitch API."""
        if not self.session_id: return
        
        url = "https://api.twitch.tv/helix/eventsub/subscriptions"
        headers = {
            "Client-ID": self.client_id,
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        async with aiohttp.ClientSession() as session:
            for sub in self.subscriptions:
                payload = {
                    "type": sub["type"],
                    "version": "1",
                    "condition": {"broadcaster_user_id": str(sub["broadcaster_id"])},
                    "transport": {
                        "method": "websocket",
                        "session_id": self.session_id
                    }
                }
                
                try:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 202:
                            print(f"[EventSub] Subscribed to {sub['type']}")
                        elif resp.status == 409:
                            # Already subscribed via WebSocket session probably shouldn't happen for new session
                            # But if we are reconnecting it might?
                            # Actually 409 usually means duplicate sub for same transport, but session IDs represent unique transports.
                            # Usually 409 is for webhooks. For websockets it's unique per session.
                            print(f"[EventSub] Subscription conflict (409)")
                        else:
                            print(f"[EventSub] Failed to subscribe: {await resp.text()}")
                except Exception as e:
                    print(f"[EventSub] Subscription error: {e}")

    async def reconnect(self, url: str):
        if self.websocket:
            await self.websocket.close()
        self.websocket = await websockets.connect(url)
        asyncio.create_task(self.listen())
