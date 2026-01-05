#!/usr/bin/env python3
"""
Twitch Token Generator
Generates OAuth tokens for broadcaster and bot accounts using Twitch OAuth
"""

import requests
import webbrowser
import time
import os
import sys
import json
from urllib.parse import urlencode, parse_qs, urlparse
import http.server
import socketserver
import threading

# All available Twitch API scopes (77 total)
SCOPES = [
    # Analytics
    "analytics:read:extensions",
    "analytics:read:games",
    # Bits
    "bits:read",
    # Channel
    "channel:edit:commercial",
    "channel:manage:ads",
    "channel:manage:broadcast",
    "channel:manage:extensions",
    "channel:manage:moderators",
    "channel:manage:polls",
    "channel:manage:predictions",
    "channel:manage:raids",
    "channel:manage:redemptions",
    "channel:manage:schedule",
    "channel:manage:videos",
    "channel:manage:vips",
    "channel:read:ads",
    "channel:read:charity",
    "channel:read:editors",
    "channel:read:goals",
    "channel:read:hype_train",
    "channel:read:polls",
    "channel:read:predictions",
    "channel:read:redemptions",
    "channel:read:stream_key",
    "channel:read:subscriptions",
    "channel:read:vips",
    # Chat
    "chat:edit",
    "chat:read",
    # Clips
    "clips:edit",
    # Moderation
    "moderation:read",
    "moderator:manage:announcements",
    "moderator:manage:automod",
    "moderator:manage:automod_settings",
    "moderator:manage:banned_users",
    "moderator:manage:blocked_terms",
    "moderator:manage:chat_messages",
    "moderator:manage:chat_settings",
    "moderator:manage:shield_mode",
    "moderator:manage:shoutouts",
    "moderator:manage:warnings",
    "moderator:read:automod_settings",
    "moderator:read:blocked_terms",
    "moderator:read:chat_settings",
    "moderator:read:chatters",
    "moderator:read:followers",
    "moderator:read:shield_mode",
    "moderator:read:shoutouts",
    "moderator:read:suspicious_users",
    "moderator:read:unban_requests",
    "moderator:read:warnings",
    # User
    "user:edit",
    "user:edit:broadcast",
    "user:edit:follows",
    "user:manage:blocked_users",
    "user:manage:chat_color",
    "user:manage:whispers",
    "user:read:blocked_users",
    "user:read:broadcast",
    "user:read:chat",
    "user:read:email",
    "user:read:follows",
    "user:read:moderated_channels",
    "user:read:subscriptions",
    "user:write:chat",
    # Whispers
    "whispers:edit",
    "whispers:read",
]

authorization_code = None
server = None

def print_header(text):
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def print_success(text):
    print(f"✅ {text}")

def print_error(text):
    print(f"❌ {text}")

def print_info(text):
    print(f"ℹ️  {text}")

class OAuthHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        global authorization_code
        parsed_path = urlparse(self.path)
        query_params = parse_qs(parsed_path.query)
        
        if 'code' in query_params:
            authorization_code = query_params['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"""
                <html>
                <head><title>Authorization Successful</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: #9146FF;">Authorization Successful!</h1>
                    <p>You can close this window and return to the terminal.</p>
                </body>
                </html>
            """)
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Error: No authorization code received</h1></body></html>")
    
    def log_message(self, format, *args):
        pass

def start_local_server(port):
    global server
    server = socketserver.TCPServer(("", port), OAuthHandler)
    server.allow_reuse_address = True
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    return server

def stop_local_server():
    global server
    if server:
        try:
            server.shutdown()
            server.server_close()
            time.sleep(0.5)  # Give it time to release the port
        except:
            pass
        server = None

def exchange_code_for_tokens(client_id, client_secret, code, redirect_uri):
    try:
        token_url = "https://id.twitch.tv/oauth2/token"
        data = {
            'client_id': client_id,
            'client_secret': client_secret,
            'code': code,
            'grant_type': 'authorization_code',
            'redirect_uri': redirect_uri
        }
        response = requests.post(token_url, data=data, timeout=10)
        if response.status_code == 200:
            token_data = response.json()
            return token_data.get('access_token'), token_data.get('refresh_token')
        else:
            print_error(f"Token exchange failed: {response.status_code}")
            print_error(f"Response: {response.text}")
            return None, None
    except Exception as e:
        print_error(f"Error exchanging code for tokens: {e}")
        return None, None

def generate_tokens_oauth(account_type, client_id, client_secret, port):
    global authorization_code
    authorization_code = None
    redirect_uri = f"http://localhost:{port}"
    
    try:
        print_info(f"Starting {account_type} OAuth flow on port {port}...")
        scope_str = " ".join(SCOPES)
        auth_params = {
            'client_id': client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': scope_str
        }
        auth_url = f"https://id.twitch.tv/oauth2/authorize?{urlencode(auth_params)}"
        print_info(f"Opening browser for {account_type} authorization...")
        print_info(f"Make sure you're logged into your {account_type.upper()} Twitch account!")
        input(f"\nPress Enter to open browser for {account_type} authorization...")
        
        start_local_server(port)
        webbrowser.open(auth_url)
        print_info(f"Waiting for {account_type} authorization...")
        print_info("Please complete the authorization in your browser")
        
        max_wait = 300
        elapsed = 0
        while authorization_code is None and elapsed < max_wait:
            time.sleep(1)
            elapsed += 1
            if elapsed % 30 == 0:
                print_info(f"Still waiting for {account_type}... ({elapsed}s elapsed)")
        
        stop_local_server()
        
        if authorization_code is None:
            print_error(f"{account_type} authorization timed out")
            return None, None
        
        print_success(f"{account_type} authorization code received!")
        print_info("Exchanging code for tokens...")
        access_token, refresh_token = exchange_code_for_tokens(client_id, client_secret, authorization_code, redirect_uri)
        
        if access_token and refresh_token:
            print_success(f"{account_type} tokens generated successfully!")
            return access_token, refresh_token
        else:
            return None, None
    except Exception as e:
        print_error(f"{account_type} token generation failed: {e}")
        stop_local_server()
        return None, None

def save_tokens_to_env(broadcaster_access, broadcaster_refresh, bot_access, bot_refresh):
    try:
        env_file = os.path.join(os.path.dirname(__file__), '..', '.env')
        print_info(f"Updating .env file at: {os.path.abspath(env_file)}")
        
        env_lines = []
        if os.path.exists(env_file):
            with open(env_file, 'r', encoding='utf-8') as f:
                env_lines = f.readlines()
        
        tokens_to_update = {
            'BROADCASTER_TOKEN': f'oauth:{broadcaster_access}',
            'BROADCASTER_REFRESH_TOKEN': broadcaster_refresh,
            'BOT_TOKEN': f'oauth:{bot_access}',
            'BOT_REFRESH_TOKEN': bot_refresh
        }
        
        updated = {key: False for key in tokens_to_update.keys()}
        
        for i, line in enumerate(env_lines):
            for key, value in tokens_to_update.items():
                if line.startswith(f'{key}='):
                    env_lines[i] = f'{key}={value}\n'
                    updated[key] = True
        
        for key, value in tokens_to_update.items():
            if not updated[key]:
                env_lines.append(f'{key}={value}\n')
        
        with open(env_file, 'w', encoding='utf-8') as f:
            f.writelines(env_lines)
        
        print_success("All tokens saved to .env file!")
        print_info("Tokens saved:")
        print_info("  - BROADCASTER_TOKEN (with oauth: prefix)")
        print_info("  - BROADCASTER_REFRESH_TOKEN")
        print_info("  - BOT_TOKEN (with oauth: prefix)")
        print_info("  - BOT_REFRESH_TOKEN")
    except Exception as e:
        print_error(f"Failed to save tokens: {e}")
        sys.exit(1)

def load_credentials():
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return None
    return None

def save_credentials(broadcaster_id, broadcaster_secret, bot_id, bot_secret):
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    credentials = {
        'broadcaster_client_id': broadcaster_id,
        'broadcaster_client_secret': broadcaster_secret,
        'bot_client_id': bot_id,
        'bot_client_secret': bot_secret
    }
    try:
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(credentials, f, indent=4)
        print_success("Credentials saved for future use!")
    except Exception as e:
        print_error(f"Failed to save credentials: {e}")

def main():
    print_header("Twitch Token Generator")
    print("\nThis tool generates OAuth tokens for your Twitch bot.")
    print("\nAll 77 available Twitch scopes will be requested.")
    input("\nPress Enter to continue...")
    
    saved_creds = load_credentials()
    
    print_header("Step 1/2: Broadcaster Account")
    if saved_creds:
        print_info("Found saved credentials!")
        print(f"Broadcaster Client ID: {saved_creds.get('broadcaster_client_id', 'N/A')}")
        use_saved = input("\nUse saved credentials? (Y/n): ").strip().lower()
        if use_saved in ['', 'y', 'yes']:
            broadcaster_client_id = saved_creds.get('broadcaster_client_id')
            broadcaster_client_secret = saved_creds.get('broadcaster_client_secret')
            print_success("Using saved broadcaster credentials")
        else:
            print("\nEnter your BROADCASTER account credentials:")
            broadcaster_client_id = input("Broadcaster Client ID: ").strip()
            broadcaster_client_secret = input("Broadcaster Client Secret: ").strip()
    else:
        print("\nEnter your BROADCASTER account credentials:")
        broadcaster_client_id = input("Broadcaster Client ID: ").strip()
        broadcaster_client_secret = input("Broadcaster Client Secret: ").strip()
    
    if not broadcaster_client_id or not broadcaster_client_secret:
        print_error("Client ID and Secret are required!")
        sys.exit(1)
    
    print("\nYou will now authorize your BROADCASTER (main streamer) account.")
    print("Make sure you're logged into your broadcaster account in your browser!")
    
    broadcaster_access, broadcaster_refresh = generate_tokens_oauth("Broadcaster", broadcaster_client_id, broadcaster_client_secret, 3000)
    if not broadcaster_access or not broadcaster_refresh:
        print_error("Failed to generate broadcaster tokens. Exiting.")
        sys.exit(1)
    
    print_header("Step 2/2: Bot Account")
    if saved_creds:
        print(f"Bot Client ID: {saved_creds.get('bot_client_id', 'N/A')}")
        use_saved = input("\nUse saved bot credentials? (Y/n): ").strip().lower()
        if use_saved in ['', 'y', 'yes']:
            bot_client_id = saved_creds.get('bot_client_id')
            bot_client_secret = saved_creds.get('bot_client_secret')
            print_success("Using saved bot credentials")
        else:
            print("\nEnter your BOT account credentials:")
            bot_client_id = input("Bot Client ID: ").strip()
            bot_client_secret = input("Bot Client Secret: ").strip()
    else:
        print("\nEnter your BOT account credentials:")
        bot_client_id = input("Bot Client ID: ").strip()
        bot_client_secret = input("Bot Client Secret: ").strip()
    
    if not bot_client_id or not bot_client_secret:
        print_error("Client ID and Secret are required!")
        sys.exit(1)
    
    save_credentials(broadcaster_client_id, broadcaster_client_secret, bot_client_id, bot_client_secret)
    
    print("\nYou will now authorize your BOT (secondary) account.")
    print("⚠️  IMPORTANT: Switch to your BOT account in your browser before proceeding!")
    input("\nPress Enter when you're ready to authorize the bot account...")
    
    bot_access, bot_refresh = generate_tokens_oauth("Bot", bot_client_id, bot_client_secret, 3001)
    if not bot_access or not bot_refresh:
        print_error("Failed to generate bot tokens. Exiting.")
        sys.exit(1)
    
    print_header("Saving Tokens")
    save_tokens_to_env(broadcaster_access, broadcaster_refresh, bot_access, bot_refresh)
    
    print_header("Success!")
    print("\n✅ All tokens have been generated and saved!")
    print("\nYou can now start your bot with the new tokens.")
    print("\nPress Enter to exit...")
    input()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Token generation cancelled by user.")
        try:
            stop_local_server()
        except:
            pass
        sys.exit(0)
    except Exception as e:
        print_error(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        try:
            stop_local_server()
        except:
            pass
        sys.exit(1)
