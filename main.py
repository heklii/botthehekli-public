import json
import os
import sys
import random
import datetime
from twitchio.ext import commands
from twitchio import Client
from config import TWITCH_TOKEN, BROADCASTER_TOKEN, CHANNEL, COMMANDS_FILE, CLIENT_ID, CLIENT_SECRET, ALIASES_FILE, COMMAND_ALIASES_FILE, PERMISSIONS, SPOTIFY_SCOPES, COOLDOWNS_FILE, SETTINGS_FILE, RESPONSES_FILE
from engine import NightbotEngine
import time
from spotify_manager import SpotifyManager
from cider_manager import CiderManager
from eventsub_client import EventSubClient
from token_manager import TokenManager
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import asyncio
import requests # Added for Gist sync

from timers import TimerManager

class DataFileHandler(FileSystemEventHandler):
    """Watches for changes to data files and auto-reloads them."""
    def __init__(self, bot):
        self.bot = bot
        self.last_modified = {}
        
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Check which file was modified
        filename = os.path.basename(event.src_path)
        
        # Debounce: ignore if modified within last second
        now = time.time()
        if filename in self.last_modified and now - self.last_modified[filename] < 1.0:
            return
        self.last_modified[filename] = now
        
        # Reload appropriate data based on filename with error handling
        try:
            if filename == 'settings.json':
                asyncio.run_coroutine_threadsafe(self.bot._reload_settings(), self.bot.loop)
                print("🔄 Reloaded settings.json")
            elif filename == 'commands.json':
                self.bot.load_commands()
                print("🔄 Reloaded commands.json")
                # Auto-sync to Gist when file changes manually
                import threading
                threading.Thread(target=self.bot.export_web_data).start()
            elif filename == 'command_aliases.json':
                self.bot.load_command_aliases()
                print("🔄 Reloaded command_aliases.json")
            elif filename == 'game_aliases.json':
                self.bot.load_game_aliases()
                print("🔄 Reloaded game_aliases.json")
            elif filename == 'permissions.json':
                self.bot.load_permissions()
                print("🔄 Reloaded permissions.json")
            elif filename == 'cooldowns.json':
                self.bot.load_cooldowns()
                print("🔄 Reloaded cooldowns.json")
            elif filename == 'counts.json':
                self.bot.engine.load_counts()
                print("🔄 Reloaded counts.json")
            elif filename == 'responses.json':
                self.bot.load_responses()
                print("🔄 Reloaded responses.json")
        except json.JSONDecodeError as e:
            print(f"⚠️ Warning: Failed to reload {filename} - Invalid JSON (likely being written). Will retry on next change.")
        except Exception as e:
            print(f"⚠️ Warning: Failed to reload {filename}: {e}")

class ContextWrapper:
    """Wraps TwitchIO context to provide what Engine needs"""
    def __init__(self, ctx, command_name=None):
        self.ctx = ctx
        self.author = ctx.author
        self.content = ctx.message.content
        self.channel_name = ctx.channel.name
        self.bot = ctx.bot
        self.command_name = command_name  # For $(count) variable
        
        # Parse args: content without the command name
        parts = self.content.split(' ', 1)
        self.args = parts[1].split(' ') if len(parts) > 1 else []

class Bot(commands.Bot):
    def __init__(self):
        # Dynamically fetch token to ensure we have the latest refreshed value
        token = os.getenv('BOT_TOKEN')
        super().__init__(
            token=token,
            prefix='!',
            initial_channels=[CHANNEL]
        )
        self.engine = NightbotEngine()
        self.spotify = SpotifyManager()
        self.cider = CiderManager()
        self.token_manager = TokenManager()  # Token validation and refresh
        self.custom_commands = {}
        self.command_aliases = {}  # Aliases for commands
        self.game_aliases = {}
        self.active_chatters = set()
        self.timers = TimerManager(self)
        self.eventsub = None
        self.broadcaster_id = None
        self.permissions = {}
        self.responses = {}
        self.cooldowns = {} # {cmd_name: seconds}
        self.cooldown_state = {} # {cmd_name: last_used_timestamp}
        self.settings = {}
        self.song_request_reward_id = None  # Will store created reward ID
        
        self.load_commands()
        self.load_command_aliases()
        self.load_game_aliases()
        self.load_permissions()
        self.load_responses()
        self.load_cooldowns()
        self.load_settings()
        
        # Setup file watcher for data directory
        self.file_observer = Observer()
        self.file_handler = DataFileHandler(self)
        data_dir = os.path.join(os.path.dirname(__file__), 'data')
        self.file_observer.schedule(self.file_handler, data_dir, recursive=False)
        self.file_observer.start()
        print(f"[INFO] Watching data files for changes...")

    def stop(self):
        """Stops the bot safely from another thread."""
        if self.loop and self.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.close(), self.loop)
            try:
                future.result(timeout=5)
            except Exception as e:
                print(f"Error checking stop result: {e}")


    def load_settings(self):
        self.settings = {"disable_requests_offline": False}
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.settings.update(json.load(f))
            except Exception as e:
                print(f"Error loading settings: {e}")
    
    async def _reload_settings(self):
        """Async method to reload settings without restarting bot."""
        self.load_settings()
        
        # Sync reward status with new settings
        enabled = self.settings.get('spotify_requests_enabled', True)
        if self.song_request_reward_id:
             await self.update_song_request_reward_status(enabled)
             
        print("✅ Settings reloaded successfully")

    def save_settings(self):
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")

    async def is_stream_live(self):
        """Check if the stream is currently live."""
        try:
            # TwitchIO 2.x method to fetch streams
            # Note: fetch_streams takes user_ids or user_logins
            # We use self.fetch_users to get the ID usually, but we can pass login directly?
            # actually fetch_streams(user_logins=[CHANNEL]) works
            streams = await self.fetch_streams(user_logins=[CHANNEL])
            return len(streams) > 0
        except Exception as e:
            print(f"Error checking stream status: {e}")
            return False

    def load_cooldowns(self):
        self.cooldowns = {}
        if os.path.exists(COOLDOWNS_FILE):
            try:
                with open(COOLDOWNS_FILE, 'r', encoding='utf-8') as f:
                    self.cooldowns = json.load(f)
            except Exception as e:
                print(f"Error loading cooldowns: {e}")
                
    def check_cooldown(self, cmd_name):
        """Returns True if command is on cooldown, False otherwise (and updates time)."""
        if cmd_name not in self.cooldowns:
            return False
            
        duration = self.cooldowns[cmd_name]
        last_used = self.cooldown_state.get(cmd_name, 0)
        now = time.time()
        
        if now - last_used < duration:
            return True
            
        self.cooldown_state[cmd_name] = now
        return False

        self.load_responses()

    def load_permissions(self):
        perm_file = os.path.join(os.path.dirname(__file__), 'data', 'permissions.json')
        if os.path.exists(perm_file):
            try:
                with open(perm_file, 'r', encoding='utf-8') as f:
                    self.permissions = json.load(f)
                print(f"[OK] Loaded permissions from {perm_file}")
            except Exception as e:
                print(f"Error loading permissions: {e}")
                # Fallback to defaults
                self.permissions = PERMISSIONS.copy()
        else:
            # First time: use config defaults and save them
            self.permissions = PERMISSIONS.copy()
            self.save_permissions()
            print(f"[OK] Created permissions.json from config defaults")
            
        # Always sync to catch new commands
        self.sync_permissions()
                
    def save_permissions(self):
        perm_file = os.path.join(os.path.dirname(__file__), 'data', 'permissions.json')
        try:
            with open(perm_file, 'w', encoding='utf-8') as f:
                json.dump(self.permissions, f, indent=4)
        except Exception as e:
            print(f"Error saving permissions: {e}")

    def sync_permissions(self):
        """Ensure all commands (native and custom) are in permissions.json."""
        msg_buffer = []
        changed = False
        
        # 1. Check Native Commands
        public_native = ['!song']
        for cmd_name in self.commands:
            full_cmd = f"!{cmd_name}"
            if full_cmd not in self.permissions:
                if full_cmd in public_native:
                    self.permissions[full_cmd] = ["everyone"]
                else:
                    self.permissions[full_cmd] = ["moderator", "broadcaster"]
                msg_buffer.append(f"Added {full_cmd}")
                changed = True
                
        # 2. Check Custom Commands
        for cmd_name in self.custom_commands:
            # Respect original name (don't force prefix)
            full_cmd = cmd_name
            if full_cmd not in self.permissions:
                self.permissions[full_cmd] = ["everyone"]
                msg_buffer.append(f"Added {full_cmd}")
                changed = True
        
        if changed:
            self.save_permissions()
            print(f"Synced permissions: {', '.join(msg_buffer)}")

    def check_permission(self, ctx, command_name):
        """Check if user has permission to run command."""
        # 1. Broadcaster always allows
        if ctx.author.is_broadcaster:
            return True
            
        # 2. Check explicit roles in config/json
        # Normalize command name
        # Normalize command name
        cmd = command_name.lower()
        
        # Determine effective permission key
        perm_key = None
        if cmd in self.permissions:
            perm_key = cmd
        elif not cmd.startswith('!') and ('!' + cmd) in self.permissions:
            perm_key = '!' + cmd
            
        if perm_key:
            allowed_roles = self.permissions[perm_key]
            if 'everyone' in allowed_roles:
                return True
            if 'moderator' in allowed_roles and ctx.author.is_mod:
                return True
            if 'subscriber' in allowed_roles and ctx.author.is_subscriber:
                return True
            if 'vip' in allowed_roles and ctx.author.is_vip:
                return True
            
            # If command is restricted and user doesn't meet requirements, return False
            return False
        
        # 3. Default fallback if not defined
        return True

    def load_responses(self):
        self.responses = {} # Reset
        if os.path.exists(RESPONSES_FILE):
            try:
                with open(RESPONSES_FILE, 'r', encoding='utf-8') as f:
                    self.responses = json.load(f)
            except Exception as e:
                print(f"Error loading responses: {e}")

    def save_responses(self):
        try:
            with open(RESPONSES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.responses, f, indent=4)
        except Exception as e:
            print(f"Error saving responses: {e}")

    def get_response(self, key, default):
        # Handle new nested structure: {'key': {'template': '...', 'description': '...'}}
        if key in self.responses:
            val = self.responses[key]
            if isinstance(val, dict):
                return val.get('template', default)
            return val # Fallback for old style string
        return default

    async def send_response(self, ctx, template_key, variables):
        """Format template and send response - STRICTLY uses responses.json."""
        # Check if response exists
        if template_key not in self.responses:
            print(f"ERROR: Response key '{template_key}' not found in responses.json!")
            await ctx.send(f"[Bot Error: Missing response template '{template_key}']")
            return
        
        response_data = self.responses[template_key]
        
        # Check if response is enabled
        if isinstance(response_data, dict):
            if not response_data.get('enabled', True):
                # Response is disabled, don't send
                return
            template = response_data.get('template', '')
        else:
            # Legacy string format
            template = str(response_data)
        
        if not template:
            print(f"ERROR: Response key '{template_key}' has empty template!")
            return
        
        # 1. Python Formatting (e.g. {track_name})
        try:
            formatted = template.format(**variables)
        except KeyError as e:
            formatted = template # fallback if var missing
            print(f"Missing variable in template {template_key}: {e}")
            
        # 2. Nightbot Variable Processing (e.g. $(user))
        ctx_wrapper = ContextWrapper(ctx, command_name=None)
        final_reply = await self.engine.process_response(formatted, ctx_wrapper)
        
        await ctx.send(final_reply)

    async def get_broadcaster_id(self):
        """Fetch broadcaster ID."""
        try:
            users = await self.fetch_users(names=[CHANNEL])
            if users:
                return str(users[0].id)
        except Exception as e:
            print(f"Error fetching broadcaster ID: {e}")
        return None

    def load_commands(self):
        """Load custom commands."""
        self.custom_commands = {}
        if os.path.exists(COMMANDS_FILE):
            try:
                with open(COMMANDS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    if isinstance(data, list):
                        # Convert list format to dict
                        for item in data:
                            trigger = item.get('trigger')
                            if trigger and trigger != '!clip':
                                self.custom_commands[trigger] = item
                    elif isinstance(data, dict):
                        # Handle dict format
                        for cmd, response in data.items():
                            if cmd != '!clip':
                                self.custom_commands[cmd] = response
            except Exception as e:
                print(f"Error loading commands: {e}")
        print(f"Loaded {len(self.custom_commands)} custom commands.")

    def save_commands(self):
        with open(COMMANDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.custom_commands, f, indent=4, ensure_ascii=False)
        self.export_web_data() # Trigger website sync

    def export_web_data(self):
        """Export commands to web/data.json and update Gist if configured"""
        try:
            # 1. Gather all data
            web_data = []
            
            # Custom Commands
            for cmd, data in self.custom_commands.items():
                # Handle both string (legacy) and dict (new) formats
                response_text = ""
                if isinstance(data, dict):
                    response_text = data.get("response", "")
                else:
                    response_text = str(data)

                perm = self.get_command_permission(cmd)
                web_data.append({
                    "trigger": cmd,
                    "response": response_text,
                    "permission": perm,
                    "type": "Custom"
                })
            
            # NOTE: Native commands and Aliases are excluded per user request
            # to keep the website list clean.
            
            # Application: Exception for !clip (Native but requested to be shown)
            clip_perm = self.get_command_permission('!clip')
            web_data.append({
                "trigger": "!clip",
                "response": "Create a clip of the last 30s",
                "permission": clip_perm,
                "type": "Custom" # Label as Custom so it looks consistent on site
            })

            # Sort alphabetically by trigger
            web_data.sort(key=lambda x: x['trigger'].lower())

            # 2. Save locally (always)
            web_dir = os.path.join(os.path.dirname(__file__), 'web')
            os.makedirs(web_dir, exist_ok=True)
            local_path = os.path.join(web_dir, 'data.json')
            with open(local_path, 'w', encoding='utf-8') as f:
                json.dump(web_data, f, indent=4)
                
            # 3. Update Gist (if configured)
            from config import load_env_file
            env = load_env_file()
            token = env.get('GITHUB_TOKEN')
            gist_id = env.get('GIST_ID')
            
            if token and gist_id:
                print(f"🔄 Syncing {len(web_data)} commands to Gist {gist_id}...")
                
                # Debug: Show preview of first item to verify text/object issue
                if len(web_data) > 0:
                    print(f"🧐 Payload Preview (Item 0): {json.dumps(web_data[0], ensure_ascii=False)}")

                headers = {
                    "Authorization": f"Bearer {token}",
                    "X-GitHub-Api-Version": "2022-11-28",
                    "Accept": "application/vnd.github+json"
                }
                payload = {
                    "files": {
                        "data.json": {
                            "content": json.dumps(web_data, indent=4)
                        }
                    }
                }
                r = requests.patch(f"https://api.github.com/gists/{gist_id}", headers=headers, json=payload)
                if r.status_code == 200:
                    print(f"✅ Gist synced successfully!")
                else:
                    print(f"❌ Gist sync failed: {r.status_code} {r.text}")
                    
        except Exception as e:
            print(f"❌ Error exporting web data: {e}")

    def get_command_permission(self, cmd_name):
        """Helper to get permission string for a command"""
        if not hasattr(self, 'permissions'): return "everyone"
        return ", ".join(self.permissions.get(cmd_name, ["everyone"]))

    def load_game_aliases(self):
        if os.path.exists(ALIASES_FILE):
            with open(ALIASES_FILE, 'r', encoding='utf-8') as f:
                self.game_aliases = json.load(f)
        print(f"Loaded {len(self.game_aliases)} game aliases.")
        
    def load_command_aliases(self):
        """Load command aliases (e.g., !tip -> !donate)"""
        if os.path.exists(COMMAND_ALIASES_FILE):
            with open(COMMAND_ALIASES_FILE, 'r', encoding='utf-8') as f:
                self.command_aliases = json.load(f)
        print(f"Loaded {len(self.command_aliases)} command alias mappings.")
        
    def save_command_aliases(self):
         with open(COMMAND_ALIASES_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.command_aliases, f, indent=4, ensure_ascii=False)
    
    def reload_data(self, data_type=None):
        """
        Reload bot data from files without restarting.
        
        Args:
            data_type: Specific type to reload ('commands', 'aliases', 'permissions', etc.)
                       or None to reload everything
        """
        if data_type is None or data_type == 'commands':
            self.load_commands()
            print("✅ Reloaded custom commands")
        
        if data_type is None or data_type == 'aliases':
            self.load_command_aliases()
            print("✅ Reloaded command aliases")
        
        if data_type is None or data_type == 'game_aliases':
            self.load_game_aliases()
            print("✅ Reloaded game aliases")
        
        if data_type is None or data_type == 'permissions':
            self.load_permissions()
            print("✅ Reloaded permissions")
        
        if data_type is None or data_type == 'responses':
            self.load_responses()
            print("✅ Reloaded response templates")
        
        if data_type is None or data_type == 'cooldowns':
            self.load_cooldowns()
            print("✅ Reloaded cooldowns")
        
        if data_type is None or data_type == 'settings':
            self.load_settings()
            print("✅ Reloaded settings")

    async def event_ready(self):
        print(f'Logged in as | {self.nick}')
        print(f'User id is | {self.user_id}')
        
        # Validate and refresh tokens on startup
        await self.token_manager.validate_and_refresh_tokens()
        
        # Start periodic token validation (every 24 hours)
        self.loop.create_task(self.token_manager.start_periodic_validation())
        
        # Start timers
        self.loop.create_task(self.timers.start())
        
        # Setup EventSub if keys present
        # Setup EventSub if keys present
        if self.token_manager.broadcaster_token and CLIENT_ID:
            self.broadcaster_id = await self.get_broadcaster_id()
            if self.broadcaster_id:
                token = self.token_manager.broadcaster_token.replace("oauth:", "")
                self.eventsub = EventSubClient(CLIENT_ID, token)
                await self.eventsub.connect()
                # Subscribe to channel points
                self.eventsub.subscribe_channel_points(self.broadcaster_id, self.on_channel_point_redemption)
                print(f"EventSub connected for channel {CHANNEL} (ID: {self.broadcaster_id})")
                
                # Create song request reward if enabled
                if self.settings.get('song_request_reward', {}).get('enabled', False):
                    await self.create_song_request_reward()
                    
                # Sync reward paused state with spotify_requests_enabled setting
                enabled = self.settings.get('spotify_requests_enabled', True)
                if self.song_request_reward_id:
                    await self.update_song_request_reward_status(enabled)

    async def _add_to_queue_with_retry(self, ctx, query, playlist_url, max_retries=1):
        """Helper to retry adding to queue on transient API errors."""
        attempt = 0
        while attempt <= max_retries:
            success, code, track = self.spotify.add_to_queue(query, playlist_url)
            
            if success:
                return success, code, track
            
            # Use error codes that warrant a retry
            retryable_codes = ["SPOTIFY_API_ERROR", "QUEUE_TIMEOUT", "SEARCH_TIMEOUT", "SEARCH_ERROR"]
            
            if code in retryable_codes:
                if attempt < max_retries:
                    print(f"⚠️ Spotify API error ({code}). Retrying in 5s...")
                    
                    # Notify user if desired (and if ctx or user context available)
                    # We can use the sr_retry template
                    user_name = ctx.author.name if ctx else "User" # Fallback
                    
                    # Send retry message
                    retry_msg = await self.engine.process(
                        self.get_response("sr_retry", "⚠️ Spotify error. Retrying in 5 seconds..."),
                        {'user': user_name}
                    )
                    
                    # If we have a channel/ctx to send to
                    if ctx:
                        try:
                            await ctx.send(retry_msg)
                        except: pass
                    else:
                        # For channel points, we might not have a direct ctx, need to find channel
                        chan = self.get_channel(CHANNEL)
                        if chan:
                            await chan.send(retry_msg)

                    await asyncio.sleep(5)
                    attempt += 1
                    continue
            
            # If not retryable or max retries reached, return failure
            return success, code, track
        return False, "RETRIES_EXHAUSTED", None

    async def _resolve_and_add_to_queue(self, target_source, query, ctx=None):
        """
        Handle cross-platform adding to queue.
        target_source: 'spotify' or 'cider'
        """
        # 1. Identify input type and cross-platform needs
        is_spotify_link = "spotify.com" in query or "spotify:" in query
        is_apple_link = "music.apple.com" in query
        
        search_query = query
        source_track = None
        
        # Case A: Apple Link -> Adding to Spotify
        if target_source == 'spotify' and is_apple_link:
            print(f"🔄 Resolving Apple Music link for Spotify...")
            track_id = self.cider.extract_track_id(query)
            if track_id:
                info = self.cider.get_track_info(track_id)
                if info:
                    search_query = f"{info['artist'].replace('Apple Music', '').strip()} {info['name']}"
                    source_track = info
                    print(f"   Matches: {search_query}")
                else:
                    return False, "Could not resolve Apple Music link (Cider offline?)", None
        
        # Case B: Spotify Link -> Adding to Cider
        elif target_source == 'cider' and is_spotify_link:
            print(f"🔄 Resolving Spotify link for Cider...")
            track_id = self.spotify.extract_track_id(query)
            if track_id:
                info = self.spotify.get_track_info(track_id)
                if info:
                    search_query = f"{info['artist']} {info['name']}"
                    source_track = info
                    print(f"   Matches: {search_query}")
                else:
                    return False, "Could not resolve Spotify link", None

        # 2. Perform Add Action on Target
        if target_source == 'spotify':
            # Use existing retry logic
            playlist_url = self.settings.get('spotify_playlist_url', '')
            return await self._add_to_queue_with_retry(ctx, search_query, playlist_url)
            
        elif target_source == 'cider':
            # Direct add to Cider
            return self.cider.add_to_queue(search_query)
            
        return False, "UNKNOWN_SOURCE", None

    @commands.command(name='csr', aliases=['cider'])
    async def cmd_cider_request(self, ctx: commands.Context):
        """Request a song on Cider (Apple Music)."""
        query = ctx.message.content.replace(f"!{ctx.command.name}", "").strip()
        # Handle alias case where command name might be different
        if not query:
             # If alias used, we might need to be careful. twitchio splits it for us?
             # ctx.message.content is full message.
             # fallback split
             parts = ctx.message.content.split(' ', 1)
             if len(parts) > 1:
                 query = parts[1]
        
        if not query:
            return

        success, msg, track = await self._resolve_and_add_to_queue('cider', query, ctx)
        
        if success:
            track_name = track.get('name', 'Unknown') if track else 'Song'
            artist_name = track.get('artist', 'Unknown') if track else 'Unknown Artist'
            
            reply = f"🍎 Added {track_name} by {artist_name} to queue!"
            await ctx.send(reply)
        else:
             await ctx.send(f"⚠️ Could not add to Cider: {msg}")

    @commands.command(name='sr', aliases=['request', 'songrequest'])
    async def cmd_song_request(self, ctx: commands.Context):
        """Request a song on Spotify."""
        # Check permissions/settings
        if self.settings.get("disable_requests_offline", False):
             if not await self.is_stream_live():
                 # Offline msg
                 template = self.responses.get('sr_offline', {}).get('template', "Stream is offline.")
                 await self.send_response(ctx, 'sr_offline', {'user': ctx.author.name})
                 return

        if not self.settings.get('spotify_requests_enabled', True):
            await self.send_response(ctx, 'sr_disabled', {'user': ctx.author.name})
            return

        query = ctx.message.content.replace(f"!{ctx.command.name}", "").replace(f"!{ctx.command.name.lower()}", "").strip()
        # Fallback extraction if alias was used
        parts = ctx.message.content.split(' ', 1)
        if len(parts) > 1:
             query = parts[1]
             
        if not query:
            await ctx.send("Usage: !sr <song name or link>")
            return

        # 3. Add to Queue using new resolver
        success, msg, track = await self._resolve_and_add_to_queue('spotify', query, ctx)

        if success:
            variables = {
                'user': ctx.author.name,
                'track_name': track.get('name', 'Unknown'),
                'artist': track.get('artist', 'Unknown'),
                'url': track.get('url', ''),
                'position': 'Queue' # TODO: Get position
            }
            await self.send_response(ctx, 'sr_success', variables)
        else:
            # Check for specific error codes for better responses
            if msg == "NO_DEVICE":
                await ctx.send("⚠️ No active Spotify device found. Please open Spotify.")
            elif msg == "PREMIUM_REQUIRED":
                await ctx.send("⚠️ Spotify Premium is required for this feature.")
            else:
                await ctx.send(f"⚠️ Could not add song: {msg}")

    async def update_song_request_reward_status(self, enabled):
        """Pause or unpause the song request reward."""
        if not self.song_request_reward_id:
            return

        try:
            token = self.token_manager.broadcaster_token.replace("oauth:", "")
            client_id = await self.get_client_id(token)
            
            url = f"https://api.twitch.tv/helix/channel_points/custom_rewards?broadcaster_id={self.broadcaster_id}&id={self.song_request_reward_id}"
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # is_paused=True means DISABLED/HIDDENish
            # is_paused=False means ENABLED/VISIBLE
            data = {"is_paused": not enabled}
            
            session = await self.engine.get_session()
            async with session.patch(url, json=data, headers=headers) as resp:
                if resp.status == 200:
                    state = "ENABLED" if enabled else "PAUSED"
                    print(f"[OK] Song Request Reward is now {state}")
                else:
                    text = await resp.text()
                    print(f"⚠️ Failed to update reward status: {text}")
        except Exception as e:
            print(f"Error updating reward status: {e}")

    async def create_song_request_reward(self):
        """Create the song request channel point reward."""
        try:
            reward_config = self.settings.get('song_request_reward', {})
            title = reward_config.get('title', 'Song Request')
            cost = reward_config.get('cost', 300)
            
            token = self.token_manager.broadcaster_token.replace("oauth:", "")
            client_id = await self.get_client_id(token)
            
            url = f"https://api.twitch.tv/helix/channel_points/custom_rewards?broadcaster_id={self.broadcaster_id}"
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            data = {
                "title": title,
                "cost": cost,
                "prompt": "Enter song name or Spotify link",
                "is_enabled": True,
                "is_user_input_required": True
            }
            
            session = await self.engine.get_session()
            async with session.post(url, json=data, headers=headers) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    reward_data = result.get('data', [{}])[0]
                    self.song_request_reward_id = reward_data.get('id')
                    print(f"[OK] Created song request reward (ID: {self.song_request_reward_id})")
                else:
                    error_text = await resp.text()
                    print(f"⚠️ Could not create song request reward: {error_text}")
                    # Reward might already exist - that's okay
        except Exception as e:
            print(f"Error creating song request reward: {e}")
    
    async def update_redemption_status(self, redemption_id, reward_id, status):
        """ "Update a redemption status (FULFILLED or CANCELED)."""
        try:
            token = self.token_manager.broadcaster_token.replace("oauth:", "")
            client_id = await self.get_client_id(token)
            
            url = (f"https://api.twitch.tv/helix/channel_points/custom_rewards/redemptions"
                   f"?broadcaster_id={self.broadcaster_id}&reward_id={reward_id}&id={redemption_id}")
            
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            data = {"status": status}
            
            session = await self.engine.get_session()
            async with session.patch(url, json=data, headers=headers) as resp:
                if resp.status == 200:
                    action = "refunded" if status == "CANCELED" else "fulfilled"
                    print(f"[OK] Redemption {action}: {redemption_id}")
                    return True
                else:
                    error_text = await resp.text()
                    print(f"❌ Failed to update redemption: {error_text}")
                    return False
        except Exception as e:
            print(f"Error updating redemption status: {e}")
            return False

    async def on_channel_point_redemption(self, event_data: dict):
        """Handle channel point redemption."""
        reward = event_data.get('reward', {})
        reward_id = reward.get('id')
        reward_title = reward.get('title', '')
        user_input = event_data.get('user_input', '')
        user_name = event_data.get('user_name', 'Unknown')
        redemption_id = event_data.get('id')  # Get redemption ID for refund/fulfill
        
        print(f"Redemption: {reward_title} by {user_name}: {user_input} (ID: {redemption_id})")
        
        # Song Request handling (Unified Reward)
        if "song" in reward_title.lower() or "request" in reward_title.lower():
            if self.settings.get("disable_requests_offline", False):
                is_live = await self.is_stream_live()
                if not is_live:
                    print(f"Ignored request from {user_name} (stream offline)")
                    chan = self.get_channel(CHANNEL)
                    if chan:
                        # Use template for offline message
                        template = self.responses.get('cp_offline', {}).get('template', '@{user} Stream is offline, song requests are disabled.')
                        message = await self.engine.process(template, {'user': user_name})
                        await chan.send(message)
                    # Refund points
                    if redemption_id and reward_id:
                        await self.update_redemption_status(redemption_id, reward_id, "CANCELED")
                    return

            if user_input:
                # Check global enable switch (applies to both services generally)
                # We can check specific service enable too if we want, but "spotify_requests_enabled" 
                # might be repurposed as "music_requests_enabled" in future. For now, we trust it.
                if not self.settings.get('spotify_requests_enabled', True):
                     print(f"Ignored request from {user_name} (requests disabled)")
                     chan = self.get_channel(CHANNEL)
                     if chan:
                         # Use sr_disabled template
                         message = await self.engine.process(
                             self.get_response("sr_disabled", "Requests are disabled."), 
                             {'user': user_name}
                         )
                         await chan.send(message)
                     
                     # Always refund if it was disabled but they managed to redeem
                     if redemption_id and reward_id:
                         await self.update_redemption_status(redemption_id, reward_id, "CANCELED")
                     return

                chan = self.get_channel(CHANNEL)
                if chan:
                    # Determine Active Service
                    target_service = self.settings.get('active_music_service', 'spotify')
                    
                    if target_service == 'cider':
                         success, msg, track = await self._resolve_and_add_to_queue('cider', user_input, None)
                    else:
                         # Spotify (Default)
                         playlist_url = self.settings.get('spotify_playlist_url', '')
                         success, msg, track = await self._add_to_queue_with_retry(None, user_input, playlist_url)

                    
                    if success:
                        # Mark as fulfilled
                        if redemption_id and reward_id:
                            # Check auto-fulfill setting
                            if self.settings.get('auto_fulfill_on_success', True):
                                await self.update_redemption_status(redemption_id, reward_id, "FULFILLED")
                        
                        # Use cp_success template
                        variables = {
                            'user': user_name,
                            'track_name': track.get('name', 'Unknown'),
                            'artist': track.get('artist', 'Unknown'),
                            'service': 'Cider' if target_service == 'cider' else 'Spotify'
                        }
                        template = self.responses.get('cp_success', {}).get('template', '/me {user} requested {track_name} by {artist} 🎶')
                        message = await self.engine.process(template, variables)
                        await chan.send(message)
                    else:
                        # Check if auto-refund is enabled
                        auto_refund = self.settings.get('auto_refund_on_error', True)
                        
                        if auto_refund:
                            # Refund points
                            if redemption_id and reward_id:
                                await self.update_redemption_status(redemption_id, reward_id, "CANCELED")
                            
                            # Use cp_error_refunded template
                            variables = {
                                'user': user_name,
                                'error_message': msg
                            }
                            template = self.responses.get('cp_error_refunded', {}).get('template', '🎵 @{user} {error_message} Points have been refunded.')
                            message = await self.engine.process(template, variables)
                            await chan.send(message)
                        else:
                            # Do NOT refund
                            # Just send error message (cp_error_no_refund)
                            variables = {
                                'user': user_name,
                                'error_message': msg
                            }
                            template = self.responses.get('cp_error_no_refund', {}).get('template', '🎵 @{user} {error_message}.')
                            message = await self.engine.process(template, variables)
                            await chan.send(message)

    async def event_message(self, message):
        if message.echo:
            return

        # Track active chatters for !winner
        if message.author and message.author.name:
            self.active_chatters.add(message.author.name)

        # Track lines for timers
        self.timers.track_line()

        content = message.content
        cmd_name = None
        is_prefixed = content.startswith('!')
        
        # Check for both prefixed (!) and non-prefixed commands
        if is_prefixed:
            # Handle prefixed commands
            # First check multi-word aliases (e.g., "!editcom !duo" -> "!cd")
            matched_alias = None
            matched_main_cmd = None
            
            for main_cmd, aliases in self.command_aliases.items():
                for alias in aliases:
                    # Check if message starts with the alias
                    # Match if: exact match OR starts with alias + space
                    if content.lower() == alias.lower() or content.lower().startswith(alias.lower() + ' '):
                        matched_alias = alias
                        matched_main_cmd = main_cmd
                        break
                if matched_alias:
                    break
            
            if matched_alias:
                # Replace the alias with the main command in the message content
                # This allows both custom and native commands to work
                new_content = matched_main_cmd + content[len(matched_alias):]
                print(f"Alias matched: {matched_alias} -> {matched_main_cmd}")
                print(f"Rewritten message: {content} -> {new_content}")
                
                # Modify the message content directly
                message.content = new_content
                content = new_content
            
            # Now check if it's a custom command
            cmd_name = content.split(' ')[0].lower()
            
            if cmd_name in self.custom_commands:
                # Check permissions (manual check for custom commands)
                ctx = await self.get_context(message)
                if not self.check_permission(ctx, cmd_name):
                    return

                # Check cooldowns
                if self.check_cooldown(cmd_name):
                    # Optionally notify user or just ignore
                    print(f"Command {cmd_name} on cooldown.")
                    return

                response_template = self.custom_commands[cmd_name]
                if isinstance(response_template, dict):
                    response_template = response_template.get('response', '')

                print(f"Processing custom command: {cmd_name} -> {response_template}")
                
                # Increment count for this command
                self.engine.increment_count(cmd_name)
                
                # Create context wrapper for the engine
                ctx = await self.get_context(message)
                engine_ctx = ContextWrapper(ctx, command_name=cmd_name)
                
                try:
                    reply = await self.engine.process_response(response_template, engine_ctx)
                    await message.channel.send(reply)
                except Exception as e:
                    print(f"Error processing command {cmd_name}: {e}")
                return  # Exit early
        else:
            # Check for non-prefixed commands
            # Split message to get the first word as potential command
            first_word = content.split(' ')[0].lower()
            
            if first_word in self.custom_commands:
                # Found a non-prefixed command match
                cmd_name = first_word
                
                # Check permissions
                ctx = await self.get_context(message)
                if not self.check_permission(ctx, cmd_name):
                    return

                # Check cooldowns
                if self.check_cooldown(cmd_name):
                    print(f"Command {cmd_name} on cooldown.")
                    return

                response_template = self.custom_commands[cmd_name]
                if isinstance(response_template, dict):
                    response_template = response_template.get('response', '')

                print(f"Processing non-prefixed command: {first_word} -> {cmd_name} -> {response_template}")
                
                # Increment count for this command
                self.engine.increment_count(cmd_name)
                
                # Create context wrapper for the engine
                ctx = await self.get_context(message)
                engine_ctx = ContextWrapper(ctx, command_name=cmd_name)
                
                try:
                    reply = await self.engine.process_response(response_template, engine_ctx)
                    await message.channel.send(reply)
                except Exception as e:
                    print(f"Error processing command {cmd_name}: {e}")
                return  # Exit early

        # Handle native commands (including aliased ones) - only if message starts with !
        if is_prefixed:
            await self.handle_commands(message)

    @commands.command(name='commands', aliases=['addcom', 'delcom', 'editcom', 'command'])
    async def cmd_manage(self, ctx, *args):
        """Manage custom commands."""
        # Note: We are using a centralized permission check
        if not self.check_permission(ctx, '!commands'):
            return

        # Parse what user actually typed (e.g. !addcom) to handle aliases
        trigger = ctx.message.content.split(' ')[0]
        command_name = trigger[1:].lower() if trigger.startswith('!') else trigger.lower()
        
        action = None
        cmd_trigger = None
        response = None
        
        # Handle both !commands and !command with subcommands
        if command_name in ['commands', 'command']:
            if not args:
                action = 'list'
            else:
                action = args[0].lower()
                if len(args) > 1: cmd_trigger = args[1]
                if len(args) > 2: response = " ".join(args[2:])
        elif command_name == 'addcom':
            action = 'add'
            if len(args) > 0: cmd_trigger = args[0]
            if len(args) > 1: response = " ".join(args[1:])
        elif command_name == 'delcom':
            action = 'del'
            if len(args) > 0: cmd_trigger = args[0]
        elif command_name == 'editcom':
            action = 'edit'
            if len(args) > 0: cmd_trigger = args[0]
            if len(args) > 1: response = " ".join(args[1:])
        
        if action in ['list', None]:
            if self.custom_commands:
                # Sort commands alphabetically
                sorted_commands = sorted(self.custom_commands.keys())
                cmd_list = ", ".join(sorted_commands[:20])
                if len(self.custom_commands) > 20: cmd_list += f"... ({len(self.custom_commands)} total)"
                await ctx.send(f"Custom commands: {cmd_list}")
            else:
                await ctx.send("No custom commands.")
            return

        if action == "add":
            if not cmd_trigger or not response:
                await ctx.send("Usage: !addcom !name response")
                return
            # if not cmd_trigger.startswith('!'): cmd_trigger = '!' + cmd_trigger
            if cmd_trigger in self.commands:
                 await ctx.send(f"Cannot overwrite native command {cmd_trigger}")
                 return
            self.custom_commands[cmd_trigger.lower()] = response
            self.save_commands()
            # Sync permissions for the new command
            self.sync_permissions()
            await ctx.send(f"Command {cmd_trigger} added.")

        elif action in ["del", "delete", "remove"]:
            if not cmd_trigger:
                await ctx.send("Usage: !delcom !name")
                return
            # if not cmd_trigger.startswith('!'): cmd_trigger = '!' + cmd_trigger
            if cmd_trigger.lower() in self.custom_commands:
                del self.custom_commands[cmd_trigger.lower()]
                self.save_commands()
                await ctx.send(f"Command {cmd_trigger} deleted.")
            else:
                await ctx.send(f"Command {cmd_trigger} not found.")

        elif action == "edit":
            if not cmd_trigger or not response:
                await ctx.send("Usage: !editcom !name response")
                return
            # if not cmd_trigger.startswith('!'): cmd_trigger = '!' + cmd_trigger
            if cmd_trigger.lower() in self.custom_commands:
                self.custom_commands[cmd_trigger.lower()] = response
                self.save_commands()
                await ctx.send(f"Command {cmd_trigger} updated.")
            else:
                await ctx.send(f"Command {cmd_trigger} not found.")

    @commands.command(name='alias', aliases=['addalias', 'delalias', 'editalias'])
    async def cmd_alias_manage(self, ctx, *args):
        """Manage command aliases."""
        if not self.check_permission(ctx, '!alias'):
            return

        # Parse what user actually typed (e.g. !addalias) to handle aliases
        trigger = ctx.message.content.split(' ')[0]
        command_name = trigger[1:].lower() if trigger.startswith('!') else trigger.lower()
        
        action = None
        main_command = None
        alias_name = None
        
        if command_name == 'alias':
            if not args:
                action = 'list'
            else:
                action = args[0].lower()
                if len(args) > 1: main_command = args[1]
                if len(args) > 2: alias_name = args[2]
        elif command_name == 'addalias':
            action = 'add'
            if len(args) > 0: main_command = args[0]
            if len(args) > 1: alias_name = args[1]
        elif command_name == 'delalias':
            action = 'del'
            if len(args) > 0: alias_name = args[0]
        elif command_name == 'editalias':
            action = 'edit'
            if len(args) > 0: main_command = args[0]
            if len(args) > 1: alias_name = args[1]
        
        if action in ['list', None]:
            if self.command_aliases:
                # Sort and format aliases
                alias_pairs = []
                for main_cmd, aliases in self.command_aliases.items():
                    for alias in aliases:
                        alias_pairs.append(f"{alias}→{main_cmd}")
                alias_list = ", ".join(alias_pairs[:15])
                if len(alias_pairs) > 15: alias_list += f"... ({len(alias_pairs)} total)"
                await ctx.send(f"Command aliases: {alias_list}")
            else:
                await ctx.send("No command aliases.")
            return

        if action == "add":
            if not main_command or not alias_name:
                await ctx.send("Usage: !addalias !maincommand !alias")
                return
            if not main_command.startswith('!'): main_command = '!' + main_command
            if not alias_name.startswith('!'): alias_name = '!' + alias_name
            
            # Check if alias already exists somewhere
            for cmd, aliases in self.command_aliases.items():
                if alias_name.lower() in [a.lower() for a in aliases]:
                    await ctx.send(f"Alias {alias_name} already exists for {cmd}")
                    return
            
            # Add the alias
            if main_command.lower() not in self.command_aliases:
                self.command_aliases[main_command.lower()] = []
            self.command_aliases[main_command.lower()].append(alias_name.lower())
            self.save_command_aliases()
            await ctx.send(f"Alias {alias_name} added for {main_command}")

        elif action in ["del", "delete", "remove"]:
            if not alias_name:
                await ctx.send("Usage: !delalias !alias")
                return
            if not alias_name.startswith('!'): alias_name = '!' + alias_name
            
            # Find and remove the alias
            found = False
            for main_cmd, aliases in list(self.command_aliases.items()):
                if alias_name.lower() in [a.lower() for a in aliases]:
                    self.command_aliases[main_cmd] = [a for a in aliases if a.lower() != alias_name.lower()]
                    # Clean up empty entries
                    if not self.command_aliases[main_cmd]:
                        del self.command_aliases[main_cmd]
                    self.save_command_aliases()
                    await ctx.send(f"Alias {alias_name} deleted.")
                    found = True
                    break
            
            if not found:
                await ctx.send(f"Alias {alias_name} not found.")

        elif action == "edit":
            if not main_command or not alias_name:
                await ctx.send("Usage: !editalias !maincommand !alias")
                return
            if not main_command.startswith('!'): main_command = '!' + main_command
            if not alias_name.startswith('!'): alias_name = '!' + alias_name
            
            # Remove alias from old location
            for main_cmd, aliases in list(self.command_aliases.items()):
                if alias_name.lower() in [a.lower() for a in aliases]:
                    self.command_aliases[main_cmd] = [a for a in aliases if a.lower() != alias_name.lower()]
                    if not self.command_aliases[main_cmd]:
                        del self.command_aliases[main_cmd]
                    break
            
            # Add to new location
            if main_command.lower() not in self.command_aliases:
                self.command_aliases[main_command.lower()] = []
            self.command_aliases[main_command.lower()].append(alias_name.lower())
            self.save_command_aliases()
            await ctx.send(f"Alias {alias_name} now points to {main_command}")

    @commands.command(name='winner')
    async def cmd_winner(self, ctx):
        if not self.check_permission(ctx, '!winner'): return
        if not self.active_chatters:
            await ctx.send("No active chatters to pick from!")
            return
        winner = random.choice(list(self.active_chatters))
        await ctx.send(f"The winner is @{winner}!")

    @commands.command(name='title')
    async def cmd_title(self, ctx):
        if not self.check_permission(ctx, '!title'): return
        # Get everything after the command as the title
        parts = ctx.message.content.split(' ', 1)
        title = parts[1].strip() if len(parts) > 1 else ''
        if not title:
            try:
                users = await self.fetch_users(names=[CHANNEL])
                if users:
                    info = await self.fetch_channel(str(users[0].id))
                    await ctx.send(f"Current Title: {info.title}")
            except Exception as e:
                await ctx.send(f"Error: {e}")
            return
        try:
            users = await self.fetch_users(names=[CHANNEL])
            if users:
                 await self.process_title_update(str(users[0].id), title)
                 await ctx.send(f"Title updated to: {title}")
        except Exception as e: await ctx.send(f"Failed: {e}")

    @commands.command(name='reload')
    async def cmd_reload(self, ctx):
        """Reload bot settings."""
        if not self.check_permission(ctx, '!commands'): # Use same perm level as admin
            return
            
        self.load_settings()
        self.load_responses()
        # Also reload commands/aliases if needed, but settings is main one
        await ctx.send(f"♻️ Settings and responses reloaded. Active Service: {self.settings.get('active_music_service', 'spotify').capitalize()}")

    @commands.command(name='game')
    async def cmd_game(self, ctx):
        if not self.check_permission(ctx, '!game'): return
        
        # Get everything after the command as the game name
        parts = ctx.message.content.split(' ', 1)
        game_name = parts[1].strip() if len(parts) > 1 else ''
        
        if not game_name:
            try:
                users = await self.fetch_users(names=[CHANNEL])
                if users:
                    info = await self.fetch_channel(str(users[0].id))
                    await ctx.send(f"Current Game: {info.game_name}")
            except Exception as e:
                await ctx.send(f"Error: {e}")
            return
        
        # Alias check
        if game_name.lower() in self.game_aliases:
            game_name = self.game_aliases[game_name.lower()]
            
        try:
            games = await self.search_categories(game_name)
            if not games:
                await ctx.send(f"Game '{game_name}' not found.")
                return
            
            # Fuzzy match improvements
            # We want to pick the best match, not just the first one.
            # Twitch API usually returns decent results, but "Elden Ring" vs "Elden Ring: Shadow..." can be tricky.
            # We will use difflib to find the most similar name.
            
            import difflib
            
            target_game = games[0] # Default to first
            best_ratio = 0.0
            
            search_query_lower = game_name.lower()
            
            for game in games:
                g_name = game.name
                g_name_lower = g_name.lower()
                
                # Check for exact match (case insensitive)
                if g_name_lower == search_query_lower:
                    target_game = game
                    break # Exact match found, stop looking
                
                # Calculate similarity ratio
                ratio = difflib.SequenceMatcher(None, search_query_lower, g_name_lower).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    target_game = game
                    
            users = await self.fetch_users(names=[CHANNEL])
            if users:
                await self.process_game_update(str(users[0].id), str(target_game.id))
                await ctx.send(f"Game updated to: {target_game.name}")
                
        except Exception as e: await ctx.send(f"Failed: {e}")


    @commands.command(name='clip')
    async def cmd_clip(self, ctx):
        """Create a clip of the last 30-90 seconds."""
        # Note: Twitch Clip API doesn't allow specific duration, it captures the moment.
        if not self.check_permission(ctx, '!clip'):
            return
        if self.check_cooldown('!clip'):
            return

        try:
            broadcaster_id = await self.get_broadcaster_id()
            if not broadcaster_id:
                await ctx.send("Error: Could not determine broadcaster ID.")
                return

            # Use Broadcaster token to ensure permission
            token = self.token_manager.broadcaster_token.replace("oauth:", "")
            client_id = await self.get_client_id(token)
            
            url = f"https://api.twitch.tv/helix/clips?broadcaster_id={broadcaster_id}"
            headers = {
                "Client-ID": client_id,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            session = await self.engine.get_session()
            async with session.post(url, headers=headers) as resp:
                if resp.status == 202: # Accepted
                    data = await resp.json()
                    clip_id = data['data'][0]['id']
                    clip_url = f"https://clips.twitch.tv/{clip_id}"
                    await ctx.send(f"🎬 Clip created! {clip_url}")
                elif resp.status == 401:
                    await ctx.send("Error: Bot/Broadcaster token missing 'clips:edit' scope.")
                else:
                    text = await resp.text()
                    await ctx.send(f"Failed to create clip. (API {resp.status})")
                    print(f"Clip Error: {text}")
                    
        except Exception as e:
            await ctx.send(f"Error creating clip: {e}")
            print(f"Clip Exception: {e}")

    @commands.command(name='update')
    async def cmd_update(self, ctx):
        """Update the bot."""
        # Admin / Broadcaster only
        if not self.check_permission(ctx, '!commands'): # Using admin perm for now
            return

        await ctx.send("🔄 Starting update process... (Backup -> Pull -> Deps -> Restart)")
        
        # Trigger updater script
        try:
            # Pass our PID so updater knows who to restart/wait for logic
            # Although our updater logic currently just exits and assumes batch loop handles restart
            cmd = ["python", "updater.py"]
            
            # Using Popen to detach slightly, or validly running it
            subprocess.Popen(cmd)
            
            # We will exit shortly if updater kills us or if we choose to exit
            # If we exit now, the batch loop might restart us before updater finishes if updater takes time.
            # So the UPDATER script should be the one to kill us if it needs to replace open files.
            # OR we just wait and let updater do its thing.
            # If we are windows, replacing in-use files (.py) is tricky if we are the ones running them?
            # actually usually safe if just reading.
            # But the best pattern is: Updater starts, waits for us to Exit, or kills us. 
            # Our `updater.py` (Draft 1) doesn't kill us unless we implemented that logic.
            # Let's verify `updater.py` logic again: It terminates old process if PID is passed.
            
            # So we pass PID.
            cmd = ["python", "updater.py", "--pid", str(os.getpid())]
            subprocess.Popen(cmd)
            
        except Exception as e:
            await ctx.send(f"❌ Update launch failed: {e}")

    @commands.command(name='song')
    async def cmd_song(self, ctx):
        """Get the currently playing song."""
        # Permission check optional, usually public
        # if not self.check_permission(ctx, '!song'): return
        
        target_service = self.settings.get('active_music_service', 'spotify')
        
        if target_service == 'cider':
            success, msg, track = self.cider.get_current_track()
        else:
            success, msg, track = self.spotify.get_current_track()
            
        if success:
            variables = {
                "track_name": track.get('track_name', 'Unknown'),
                "artist": track.get('artist', 'Unknown'),
                "album": track.get('album', 'Unknown'),
                "url": track.get('url', ''),
                "user": ctx.author.name
            }
            await self.send_response(ctx, "song_success", variables)
        else:
            variables = {"error_code": msg, "user": ctx.author.name}
            # Map specific errors if needed
            response_key = "song_error"
            if msg == "SPOTIFY_NOT_CONNECTED": response_key = "spotify_not_connected"
            if msg == "SPOTIFY_NOT_CONNECTED": response_key = "spotify_not_connected"
            if msg == "CIDER_NOT_PLAYING": response_key = "song_no_track_playing" 
            
            await self.send_response(ctx, response_key, variables)

    @commands.command(name='csr', aliases=['cider'])
    async def cmd_cider_request(self, ctx: commands.Context):
        """Request a song on Cider (Apple Music)."""
        query = ctx.message.content.replace(f"!{ctx.command.name}", "").strip()
        parts = ctx.message.content.split(' ', 1)
        if len(parts) > 1:
             query = parts[1]
        
        if not query:
            return

        success, msg, track = await self._resolve_and_add_to_queue('cider', query, ctx)
        
        if success:
            variables = {
                 "track_name": track.get('name', 'Unknown'),
                 "artist": track.get('artist', 'Unknown'),
                 "position": "Queue", 
                 "query": query,
                 "url": track.get('url', ''),
                 "user": ctx.author.name
            }
            await self.send_response(ctx, "sr_success", variables)
        else:
             variables = {"error_code": msg, "query": query, "user": ctx.author.name}
             await self.send_response(ctx, "sr_error", variables)

    @commands.command(name='sr', aliases=['request', 'songrequest'])
    async def cmd_song_request(self, ctx: commands.Context):
        """Request a song on Spotify."""
        # Check permissions/settings
        if not self.check_permission(ctx, '!sr'):
            return
        if self.check_cooldown('!sr'):
            return

        if self.settings.get("disable_requests_offline", False):
             if not await self.is_stream_live():
                 # Offline msg
                 template = self.responses.get('sr_offline', {}).get('template', "Stream is offline.")
                 await self.send_response(ctx, 'sr_offline', {'user': ctx.author.name})
                 return

        if not self.settings.get('spotify_requests_enabled', True):
            await self.send_response(ctx, 'sr_disabled', {'user': ctx.author.name})
            return

        query = ctx.message.content.replace(f"!{ctx.command.name}", "").replace(f"!{ctx.command.name.lower()}", "").strip()
        # Fallback extraction if alias was used
        parts = ctx.message.content.split(' ', 1)
        if len(parts) > 1:
             query = parts[1]
             
        if not query:
            await ctx.send("Usage: !sr <song name or link>")
            return

        # Determine Active Service
        target_service = self.settings.get('active_music_service', 'spotify')
        
        if target_service == 'cider':
            # Cider Route
            success, msg, track = await self._resolve_and_add_to_queue('cider', query, ctx)
        else:
            # Spotify Route (Default)
            success, msg, track = await self._resolve_and_add_to_queue('spotify', query, ctx) 
        
        if success:
             variables = {
                 "track_name": track.get('name', 'Unknown'),
                 "artist": track.get('artist', 'Unknown'),
                 "position": "Queue", 
                 "query": query,
                 "url": track.get('url', ''),
                 "user": ctx.author.name
             }
             
             if target_service == 'cider':
                  # Use simple response for Cider since API 404s on metadata often (though we have scraper now)
                  # or just use same success template if we trust it
                  # "Added X to queue" formatted nicely
                  await self.send_response(ctx, "sr_success", variables)
             else:
                  await self.send_response(ctx, "sr_success", variables)
                  
        else:
             # Universal Error Handling
             error_code = msg
             variables = {"error_code": error_code, "query": query, "user": ctx.author.name}
             
             # Try to map specifically if it's a known code, otherwise generic sr_error
             # We can reuse Spotify's map or extend it
             error_map = {
                 "SPOTIFY_NOT_CONNECTED": "spotify_not_connected",
                 "SEARCH_NO_RESULTS": "sr_search_failed",
                 "SEARCH_TIMEOUT": "sr_timeout",
                 "SEARCH_ERROR": "sr_search_error",
                 "TRACK_INFO_FAILED": "sr_track_info_failed",
                 "QUEUE_TIMEOUT": "sr_queue_timeout",
                 "NO_DEVICE": "sr_no_device",
                 "PREMIUM_REQUIRED": "sr_premium_required",
                 "SPOTIFY_API_ERROR": "sr_api_error",
                 "QUEUE_ADD_FAILED": "sr_queue_failed"
                 # Cider errors usually come as text, so they'll fall through to default keys or just be displayed via {error_code} if template uses it
             }
             
             response_key = error_map.get(error_code, "sr_error")
             await self.send_response(ctx, response_key, variables)

    @commands.command(name='skip')
    async def cmd_skip(self, ctx):
        """Skip current song (Mod/Broadcaster only)."""
        if not self.check_permission(ctx, '!skip'):
            return
        if self.check_cooldown('!skip'):
            return
            
        success, code = self.spotify.skip_track()
        if success:
             # Might want current track info?
             variables = {"track_name": "Current Track", "user": ctx.author.name} 
             await self.send_response(ctx, "skip_success", variables)
        else:
             # Map error code to response key
             error_map = {
                 "SPOTIFY_NOT_CONNECTED": "spotify_not_connected",
                 "SKIP_FAILED": "skip_failed"
             }
             response_key = error_map.get(code, "skip_error")
             variables = {"error_code": code, "user": ctx.author.name}
             await self.send_response(ctx, response_key, variables)

    async def get_client_id(self, token):
        # Dynamically fetch Client ID from the token validation endpoint
        session = await self.engine.get_session()
        url = "https://id.twitch.tv/oauth2/validate"
        headers = {"Authorization": f"OAuth {token}"}
        async with session.get(url, headers=headers) as resp:
            if resp.status == 200:
                data = await resp.json()
                return data.get("client_id")
            else:
                return CLIENT_ID # Fallback

    async def process_title_update(self, broadcaster_id, title):
        token = self.token_manager.broadcaster_token.replace("oauth:", "")
        client_id = await self.get_client_id(token)
        session = await self.engine.get_session()
        
        url = f"https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}"
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        data = {"title": title}
        async with session.patch(url, json=data, headers=headers) as resp:
            if resp.status != 204:
                text = await resp.text()
                raise Exception(f"API {resp.status}: {text}")

    async def process_game_update(self, broadcaster_id, game_id):
        token = self.token_manager.broadcaster_token.replace("oauth:", "")
        client_id = await self.get_client_id(token)
        session = await self.engine.get_session()
        
        url = f"https://api.twitch.tv/helix/channels?broadcaster_id={broadcaster_id}"
        headers = {
            "Client-ID": client_id,
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        data = {"game_id": game_id}
        async with session.patch(url, json=data, headers=headers) as resp:
            if resp.status != 204:
                text = await resp.text()
                raise Exception(f"API {resp.status}: {text}")


if __name__ == "__main__":
    if not TWITCH_TOKEN or not CHANNEL:
        print("Error: TWITCH_TOKEN or CHANNEL not set in config/env.")
        sys.exit(1)
    
    bot = Bot()
    bot.run()
