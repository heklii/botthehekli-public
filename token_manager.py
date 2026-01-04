import aiohttp
import os
import asyncio
import json
from dotenv import load_dotenv

import sys
import io

# Force UTF-8 for Windows console support
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

load_dotenv()

async def validate_token(access_token):
    """
    Validate a Twitch OAuth token using Twitch's official validation endpoint.
    
    Args:
        access_token: OAuth token (with or without 'oauth:' prefix)
        
    Returns:
        tuple: (is_valid: bool, info: dict or None, error: str or None)
    """
    if not access_token:
        return False, None, "No token provided"
    
    # Remove oauth: prefix if present
    token = access_token.replace('oauth:', '').strip()
    
    headers = {"Authorization": f"OAuth {token}"}
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get("https://id.twitch.tv/oauth2/validate", headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return True, data, None
                elif resp.status == 401:
                    return False, None, "Token is invalid or expired"
                else:
                    return False, None, f"Validation failed with HTTP {resp.status}"
    except Exception as e:
        return False, None, f"Validation error: {str(e)}"


async def refresh_token(refresh_token, client_id, client_secret):
    """
    Refresh an access token using Twitch's official API (Silent background refresh).
    
    Args:
        refresh_token: The refresh token
        client_id: Client ID associated with the token
        client_secret: Client Secret associated with the token
        
    Returns:
        tuple: (success: bool, new_access_token: str or None, error: str or None)
    """
    if not refresh_token:
        return False, None, "No refresh token provided"
    
    if not client_id or not client_secret:
        return False, None, "Missing Client ID or Secret"
    
    url = "https://id.twitch.tv/oauth2/token"
    params = {
        'client_id': client_id,
        'client_secret': client_secret,
        'grant_type': 'refresh_token',
        'refresh_token': refresh_token
    }
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    new_token = data.get('access_token')
                    # Optionally update refresh token if a new one is returned
                    new_refresh = data.get('refresh_token') 
                    
                    if new_token:
                        # Return both new access and (potentially new) refresh token
                        # But for now the interface returns (bool, access, error)
                        # We might need to handle the new refresh token too to keep the chain alive!
                        return True, new_token, None  
                    else:
                        return False, None, "No token in response"
                else:
                    error_text = await resp.text()
                    return False, None, f"Refresh failed with HTTP {resp.status}: {error_text}"
    except Exception as e:
        return False, None, f"Refresh error: {str(e)}"


def load_generator_credentials():
    """Load client credentials from token_generator/config.json"""
    try:
        # Path relative to this file: ./token_generator/config.json
        config_path = os.path.join(os.path.dirname(__file__), 'token_generator', 'config.json')
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"⚠️ Error loading generator credentials: {e}")
    return {}


def update_env_file(key, value):
    """
    Update a specific key in the .env file while preserving all other variables.
    
    Args:
        key: Environment variable name (e.g., 'BOT_TOKEN')
        value: New value for the variable
    """
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    
    if not os.path.exists(env_path):
        print(f"Warning: .env file not found at {env_path}")
        return False
    
    try:
        # Read existing .env file
        with open(env_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Update the specific key
        updated = False
        for i, line in enumerate(lines):
            # Check if this line sets our key
            if line.strip().startswith(f"{key}="):
                lines[i] = f"{key}={value}\n"
                updated = True
                break
        
        # If key wasn't found, append it
        if not updated:
            lines.append(f"{key}={value}\n")
        
        # Write back to .env
        with open(env_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        
        print(f"✅ Updated {key} in .env file")
        return True
        
    except Exception as e:
        print(f"❌ Error updating .env file: {e}")
        return False


class TokenManager:
    """Manages automatic token validation and refresh for bot and broadcaster accounts."""
    
    def __init__(self):
        self.bot_token = os.getenv('BOT_TOKEN')
        self.bot_refresh_token = os.getenv('BOT_REFRESH_TOKEN')
        self.broadcaster_token = os.getenv('BROADCASTER_TOKEN')
        self.broadcaster_refresh_token = os.getenv('BROADCASTER_REFRESH_TOKEN')
        
        # Load credentials from token_generator
        creds = load_generator_credentials()
        self.bot_client_id = creds.get('bot_client_id')
        self.bot_client_secret = creds.get('bot_client_secret')
        self.broadcaster_client_id = creds.get('broadcaster_client_id')
        self.broadcaster_client_secret = creds.get('broadcaster_client_secret')
        
        if not self.bot_client_id:
            print("⚠️ Warning: Bot Client ID not found in token_generator/config.json")
        
    async def validate_and_refresh_bot_token(self):
        """Validate bot token and refresh if invalid."""
        print("🔍 Validating bot token...")
        
        is_valid, info, error = await validate_token(self.bot_token)
        
        if is_valid:
            print(f"✅ Bot token validated successfully (User: {info.get('login', 'unknown')})")
            return True
        
        print(f"⚠️ Bot token invalid: {error}")
        
        if not self.bot_refresh_token:
            print("❌ No bot refresh token available. Please update .env with BOT_REFRESH_TOKEN")
            return False
            
        if not self.bot_client_id or not self.bot_client_secret:
            print("❌ Cannot refresh: Missing Bot Client ID/Secret in token_generator/config.json")
            return False
        
        print("🔄 Attempting to refresh bot token (silently)...")
        success, new_token, refresh_error = await refresh_token(
            self.bot_refresh_token, 
            self.bot_client_id, 
            self.bot_client_secret
        )
        
        if success:
            # Add oauth: prefix for TwitchIO compatibility
            oauth_token = f"oauth:{new_token}"
            
            # Update .env file
            if update_env_file('BOT_TOKEN', oauth_token):
                # Update instance variable
                self.bot_token = oauth_token
                
                # Reload environment
                load_dotenv(override=True)
                
                print("✅ Bot token refreshed successfully!")
                return True
            else:
                print("❌ Failed to update .env file with new bot token")
                return False
        else:
            print(f"❌ Failed to refresh bot token: {refresh_error}")
            return False
    
    async def validate_and_refresh_broadcaster_token(self):
        """Validate broadcaster token and refresh if invalid."""
        print("🔍 Validating broadcaster token...")
        
        is_valid, info, error = await validate_token(self.broadcaster_token)
        
        if is_valid:
            print(f"✅ Broadcaster token validated successfully (User: {info.get('login', 'unknown')})")
            return True
        
        print(f"⚠️ Broadcaster token invalid: {error}")
        
        if not self.broadcaster_refresh_token:
            print("❌ No broadcaster refresh token available. Please update .env with BROADCASTER_REFRESH_TOKEN")
            return False
            
        if not self.broadcaster_client_id or not self.broadcaster_client_secret:
            print("❌ Cannot refresh: Missing Broadcaster Client ID/Secret in token_generator/config.json")
            return False
        
        print("🔄 Attempting to refresh broadcaster token (silently)...")
        success, new_token, refresh_error = await refresh_token(
            self.broadcaster_refresh_token, 
            self.broadcaster_client_id, 
            self.broadcaster_client_secret
        )
        
        if success:
            # Add oauth: prefix for TwitchIO compatibility
            oauth_token = f"oauth:{new_token}"
            
            # Update .env file
            if update_env_file('BROADCASTER_TOKEN', oauth_token):
                # Update instance variable
                self.broadcaster_token = oauth_token
                
                # Reload environment
                load_dotenv(override=True)
                
                print("✅ Broadcaster token refreshed successfully!")
                return True
            else:
                print("❌ Failed to update .env file with new broadcaster token")
                return False
        else:
            print(f"❌ Failed to refresh broadcaster token: {refresh_error}")
            return False
    
    async def validate_and_refresh_tokens(self):
        """Validate and refresh both bot and broadcaster tokens."""
        print("\n" + "="*50)
        print("🔐 TOKEN VALIDATION & REFRESH")
        print("="*50)
        
        bot_ok = await self.validate_and_refresh_bot_token()
        broadcaster_ok = await self.validate_and_refresh_broadcaster_token()
        
        print("="*50 + "\n")
        
        return bot_ok and broadcaster_ok
    
    async def start_periodic_validation(self):
        """Start a background task to validate tokens every 1 hour."""
        print("⏰ Started periodic token validation (every 1 hour)")
        
        while True:
            # Wait 1 hour (3600 seconds)
            await asyncio.sleep(3600)
            
            print("\n⏰ Performing periodic token validation...")
            await self.validate_and_refresh_tokens()


# Standalone test function
async def test_tokens():
    """Test function to manually validate and refresh tokens."""
    manager = TokenManager()
    await manager.validate_and_refresh_tokens()


if __name__ == "__main__":
    # Allow running this module directly for testing
    print("Testing token validation and refresh...")
    asyncio.run(test_tokens())
