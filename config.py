import os
from dotenv import load_dotenv

load_dotenv()

# Twitch Config
TWITCH_TOKEN = os.getenv('BOT_TOKEN')
BROADCASTER_TOKEN = os.getenv('BROADCASTER_TOKEN')
CHANNEL = os.getenv('CHANNEL')
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')

# Refresh tokens for automatic token refresh
BOT_REFRESH_TOKEN = os.getenv('BOT_REFRESH_TOKEN')
BROADCASTER_REFRESH_TOKEN = os.getenv('BROADCASTER_REFRESH_TOKEN')

# Cider Config
CIDER_TOKEN = os.getenv('CIDER_TOKEN')
CIDER_HOST = os.getenv('CIDER_HOST', 'http://localhost:10767')

# Spotify Config
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')
SPOTIFY_SCOPES = 'user-read-playback-state user-modify-playback-state user-read-currently-playing'

# Permissions Config
# Roles: 'everyone', 'subscriber', 'vip', 'moderator', 'broadcaster'
PERMISSIONS = {
    '!song': ['everyone'],
    '!sr': ['moderator', 'broadcaster'],
    '!request': ['moderator', 'broadcaster'],
    '!skip': ['moderator', 'broadcaster'],
    '!addcom': ['moderator', 'broadcaster'],
    '!editcom': ['moderator', 'broadcaster'],
    '!delcom': ['moderator', 'broadcaster'],
    '!commands': ['moderator', 'broadcaster'],
    '!title': ['moderator', 'broadcaster'],
    '!game': ['moderator', 'broadcaster'],
    '!winner': ['moderator', 'broadcaster'],
    '!alias': ['moderator', 'broadcaster']
}

# File Paths
DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
COMMANDS_FILE = os.path.join(DATA_DIR, 'commands.json')
TIMERS_FILE = os.path.join(DATA_DIR, 'timers.json')
ALIASES_FILE = os.path.join(DATA_DIR, 'game_aliases.json')
COMMAND_ALIASES_FILE = os.path.join(DATA_DIR, 'command_aliases.json')
RESPONSES_FILE = os.path.join(DATA_DIR, 'responses.json')
COOLDOWNS_FILE = os.path.join(DATA_DIR, 'cooldowns.json')
COUNTS_FILE = os.path.join(DATA_DIR, 'counts.json')
SETTINGS_FILE = os.path.join(DATA_DIR, 'settings.json')
PERMISSIONS_FILE = os.path.join(DATA_DIR, 'permissions.json')
ENV_FILE = os.path.join(os.path.dirname(__file__), '.env')

def load_env_file():
    """Manually parse .env file to get current values on disk."""
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and '=' in line and not line.startswith('#'):
                    key, val = line.split('=', 1)
                    env[key.strip()] = val.strip()
    return env

def update_env_file(updates):
    """Update specific keys in .env file while preserving comments/lines."""
    lines = []
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
    new_lines = []
    keys_updated = set()
    
    for line in lines:
        stripped = line.strip()
        if stripped and '=' in stripped and not stripped.startswith('#'):
            key = stripped.split('=', 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                keys_updated.add(key)
                continue
        new_lines.append(line)
        
    # Append new keys
    if new_lines and not new_lines[-1].endswith('\n'):
        new_lines.append('\n')
        
    for key, val in updates.items():
        if key not in keys_updated:
            new_lines.append(f"{key}={val}\n")
            
    with open(ENV_FILE, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)
    
    # Also update os.environ for current process
    for k, v in updates.items():
        os.environ[k] = str(v)
