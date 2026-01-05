# Twitch Token Generator

A standalone tool to generate OAuth tokens for your Twitch bot's broadcaster and bot accounts.

## Features

- ✅ Generates tokens for **both** broadcaster and bot accounts
- ✅ Includes **all 77 available Twitch API scopes**
- ✅ Uses standard Twitch OAuth flow with your own Client ID/Secret
- ✅ Automatically saves tokens to your project's `.env` file with `oauth:` prefix
- ✅ Saves credentials locally for easy reuse
- ✅ Simple command-line interface

## Prerequisites

- Python 3.7 or higher
- pip (Python package installer)
- Twitch Developer applications for both broadcaster and bot accounts

## Setup

### 1. Create Twitch Applications

You need **two** separate Twitch applications:

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console/apps)
2. Click "Register Your Application"
3. Create one application for your **broadcaster account**
4. Create another application for your **bot account**

For **both** applications, add these OAuth Redirect URLs:
- `http://localhost:3000`
- `http://localhost:3001`

Save the **Client ID** and **Client Secret** for each application.

### 2. Install Dependencies

Navigate to the token_generator folder and install requirements:

```bash
cd token_generator
pip install -r requirements.txt
```

### 3. Configure Credentials (Optional)

If you want to set up credentials before running:

1. Copy `config.example.json` to `config.json`
2. Fill in your Client IDs and Secrets
3. The tool will use these automatically

**Note:** `config.json` is automatically ignored by git to keep your credentials safe.

## Usage

### Quick Start

Just double-click `run_token_generator.bat` or run:

```bash
python generate_tokens.py
```

### Step-by-Step Process

1. **Enter Credentials**
   - Enter broadcaster Client ID and Secret
   - Enter bot Client ID and Secret
   - (Or use saved credentials from previous run)

2. **Authorize Broadcaster Account**
   - Press Enter to open browser
   - Log in with your **broadcaster** Twitch account
   - Authorize the application
   - Return to terminal

3. **Authorize Bot Account**
   - Press Enter to open browser
   - **IMPORTANT:** Log in with your **bot** Twitch account
   - Authorize the application
   - Return to terminal

4. **Done!**
   - All tokens are automatically saved to `../.env`
   - Credentials saved to `config.json` for next time

## Generated Tokens

The tool generates and saves these environment variables to your project's `.env` file:

- `BROADCASTER_TOKEN` - Access token with `oauth:` prefix
- `BROADCASTER_REFRESH_TOKEN` - Refresh token for broadcaster
- `BOT_TOKEN` - Access token with `oauth:` prefix
- `BOT_REFRESH_TOKEN` - Refresh token for bot

## Scopes Included

All 77 available Twitch API scopes for complete functionality:

**Analytics** (2 scopes)
- analytics:read:extensions, analytics:read:games

**Bits** (1 scope)
- bits:read

**Channel** (26 scopes)
- channel:edit:commercial, channel:manage:ads, channel:manage:broadcast, channel:manage:extensions, channel:manage:moderators, channel:manage:polls, channel:manage:predictions, channel:manage:raids, channel:manage:redemptions, channel:manage:schedule, channel:manage:videos, channel:manage:vips, channel:read:ads, channel:read:charity, channel:read:editors, channel:read:goals, channel:read:hype_train, channel:read:polls, channel:read:predictions, channel:read:redemptions, channel:read:stream_key, channel:read:subscriptions, channel:read:vips

**Chat** (2 scopes)
- chat:edit, chat:read

**Clips** (1 scope)
- clips:edit

**Moderation** (20 scopes)
- moderation:read, moderator:manage:announcements, moderator:manage:automod, moderator:manage:automod_settings, moderator:manage:banned_users, moderator:manage:blocked_terms, moderator:manage:chat_messages, moderator:manage:chat_settings, moderator:manage:shield_mode, moderator:manage:shoutouts, moderator:manage:warnings, moderator:read:automod_settings, moderator:read:blocked_terms, moderator:read:chat_settings, moderator:read:chatters, moderator:read:followers, moderator:read:shield_mode, moderator:read:shoutouts, moderator:read:suspicious_users, moderator:read:unban_requests, moderator:read:warnings

**User** (13 scopes)
- user:edit, user:edit:broadcast, user:edit:follows, user:manage:blocked_users, user:manage:chat_color, user:manage:whispers, user:read:blocked_users, user:read:broadcast, user:read:chat, user:read:email, user:read:follows, user:read:moderated_channels, user:read:subscriptions, user:write:chat

**Whispers** (2 scopes)
- whispers:edit, whispers:read

## Troubleshooting

### "Authorization timed out"
- Make sure you complete the authorization within 5 minutes
- Check that you're logged into the correct Twitch account

### "Port already in use"
- Make sure no other application is using ports 3000 or 3001
- Close any previously running token generator instances

### "Failed to save tokens"
- Ensure the `.env` file exists in the parent directory
- Check file permissions

### "Token exchange failed"
- Verify your redirect URIs are set correctly in both Twitch applications
- Ensure both `http://localhost:3000` and `http://localhost:3001` are added

### Browser doesn't open
- Manually copy the URL from the console and paste it in your browser

## Security

- **config.json** contains your Client IDs and Secrets - it's automatically excluded from git
- **Never commit** `config.json` to version control
- Your tokens are saved locally to `.env` and never transmitted anywhere except to Twitch
- The OAuth flow uses industry-standard authorization code flow

## Files

- `generate_tokens.py` - Main token generator script
- `run_token_generator.bat` - Windows batch file to run the generator
- `config.json` - Your saved credentials (auto-generated, gitignored)
- `config.example.json` - Example config file structure
- `requirements.txt` - Python dependencies
- `.gitignore` - Excludes sensitive files from git

## Notes

- **Important**: Make sure to switch to your bot account in your browser before authorizing the second time!
- The tool uses separate ports (3000 and 3001) to avoid conflicts between authorizations
- Credentials are reusable - you only need to enter them once
- Tokens include the `oauth:` prefix automatically as required by Twitch
