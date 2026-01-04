import os
import webbrowser
import asyncio
from aiohttp import web
import aiohttp
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
REDIRECT_URI = 'http://localhost:3000/callback'

if not CLIENT_ID or not CLIENT_SECRET:
    print("Error: CLIENT_ID or CLIENT_SECRET not found in .env file.")
    exit(1)

# "All the scoops" (Scopes)
SCOPES = [
    'analytics:read:extensions',
    'analytics:read:games',
    'bits:read',
    'channel:edit:commercial',
    'channel:manage:broadcast',
    'channel:read:charity',
    'channel:manage:extensions',
    'channel:manage:moderators',
    'channel:manage:polls',
    'channel:manage:predictions',
    'channel:manage:raids',
    'channel:manage:redemptions',
    'channel:manage:schedule',
    'channel:manage:videos',
    'channel:read:editors',
    'channel:read:goals',
    'channel:read:hype_train',
    'channel:read:polls',
    'channel:read:predictions',
    'channel:read:redemptions',
    'channel:read:stream_key',
    'channel:read:subscriptions',
    'channel:read:vips',
    'chat:edit',
    'chat:read',
    'clips:edit',
    'moderation:read',
    'moderator:manage:announcements',
    'moderator:manage:automod',
    'moderator:manage:banned_users',
    'moderator:manage:chat_messages',
    'moderator:manage:chat_settings',
    'moderator:manage:shoutouts',
    'moderator:read:automod_settings',
    'moderator:read:blocked_terms',
    'moderator:read:chat_settings',
    'moderator:read:chatters',
    'moderator:read:followers',
    'moderator:read:shoutouts',
    'user:edit',
    'user:edit:follows',
    'user:manage:blocked_users',
    'user:manage:chat_color',
    'user:manage:whispers',
    'user:read:blocked_users',
    'user:read:broadcast',
    'user:read:email',
    'user:read:follows',
    'user:read:subscriptions',
    'whispers:read'
]

async def handle_callback(request):
    code = request.query.get('code')
    if not code:
        return web.Response(text="Error: No code received.")

    # Exchange code for tokens
    token_url = 'https://id.twitch.tv/oauth2/token'
    params = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET,
        'code': code,
        'grant_type': 'authorization_code',
        'redirect_uri': REDIRECT_URI
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, params=params) as resp:
            data = await resp.json()

            if 'access_token' in data:
                print("\n" + "="*50)
                print("SUCCESS! HERE ARE YOUR TOKENS:")
                print("="*50)
                print(f"Access Token:\n{data['access_token']}")
                print("-" * 20)
                print(f"Refresh Token:\n{data['refresh_token']}")
                print("="*50 + "\n")
                
                return web.Response(text="Success! You can close this window and check your terminal.")
            else:
                return web.Response(text=f"Error exchanging token: {data}")

async def main():
    app = web.Application()
    app.router.add_get('/callback', handle_callback)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 3000)
    await site.start()

    # Construct Auth URL
    scope_str = " ".join(SCOPES)
    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={scope_str}"
    )

    print("Opening browser for authorization...")
    print(f"If it doesn't open, visit:\n{auth_url}")
    webbrowser.open(auth_url)

    # Keep running until user stops it (Ctrl+C)
    print("Waiting for callback on http://localhost:3000/callback ... Press Ctrl+C to stop.")
    await asyncio.Event().wait() 

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nExiting.")
