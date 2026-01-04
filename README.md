# botthehekli (Evening Bot)

A powerful, locally-hosted Twitch bot with Spotify/Cider music integration, custom commands, and a GUI control panel.

## Features
- **Twitch Integration**: Chat commands, channel points, and event subscriptions.
- **Music Integration**:
  - **Spotify**: Request songs directly to your queue or a specific playlist.
  - **Cider (Apple Music)**: Seamless integration with the Cider client for Apple Music requests.
  - **Unified Queue**: Handle requests from both services intelligently.
- **GUI Control Panel**: Manage settings, commands, and timers without touching code.
- **Dynamic Commands**: Create custom text commands and aliases.

## Installation

### Prerequisites
1.  **Python 3.10+**: Download and install from [python.org](https://www.python.org/).
    *   **Important**: Check "Add Python to PATH" during installation.
2.  **Git** (Optional but recommended): For updates.

### Setup

#### 1. Twitch Developer Application (Required)
Before running the bot, you need to create a "Project" on Twitch to get your credentials.

1.  Go to the [Twitch Developer Console](https://dev.twitch.tv/console).
2.  Click **Register Your Application**.
3.  **Name**: Anything (e.g., "MyStreamBot").
4.  **OAuth Redirect URLs**: `http://localhost:3000/callback` (Important: must match exactly).
5.  **Category**: Chat Bot.
6.  Click **Create**.
7.  Click **Manage** on your new app to see your **Client ID** and **Client Secret**.

#### 2. Configuration File
1.  Find the file named `.env.example` in this folder.
2.  Rename it to **`.env`** (Remove .example).
3.  Open `.env` with Notepad.
4.  Paste your **Client ID** and **Client Secret** (from step 1) next to `CLIENT_ID=` and `CLIENT_SECRET=`.
    *   *Note: Leave the TOKEN fields blank for now.*

#### 3. Install Dependencies
Double-click **`run_bot.bat`**. It will try to install Python libraries.
*   If it closes immediately or fails, open a terminal here and run:
    ```bash
    pip install -r requirements.txt
    ```

#### 4. Generate Tokens
Now that your `.env` has the Client ID/Secret, you need to authorize the bot to access your chat.
1.  Run **`generate_token.bat`**.
2.  A browser window will open asking you to authorize the bot.
3.  Click **Authorize**.
4.  The script will automatically grab your tokens and update the `.env` file for you.
5.  **Done!** required tokens are now saved.

#### 5. Music Setup (Spotify/Cider)

**Option A: Spotify**
To let the bot control your Spotify playback, you need a free Developer App.
1.  Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/) and log in.
2.  Click **Create App**.
3.  **App Name**: "StreamBot" (or anything).
4.  **App Description**: "Bot for stream."
5.  **Redirect URI**:
    *   Enter: `http://127.0.0.1:8888/callback`
    *   Click **Add**.
    *   *(Note: This is critical for the login popup to work).*
6.  Check "I understand" and click **Save**.
7.  Click **Settings** (top right) to see your **Client ID** and **Client Secret**.
8.  **Enter in Bot**:
    *   Open the Bot GUI (`run_gui.bat`).
    *   Go to **Music Services** tab.
    *   Select **Spotify** as Active Service.
    *   Paste your Client ID and Client Secret in the "Spotify Config" section.
    *   Click **Save All Music Settings**.
    *   *(On first run, a browser will pop up asking you to login to Spotify. Agree to it.)*

**Option B: Cider (Apple Music)**
[Cider](https://cider.sh/) is a popular 3rd-party Apple Music client.
1.  Open Cider on your PC.
2.  Go to **Settings** -> **Connectivity**.
3.  Look for **"External Application Access"** (or "RPC Integration" / "SDK").
4.  Enable it.
5.  Copy the **Host** address (usually `http://localhost:10767`) and the **Auth Token** shown there.
6.  **Enter in Bot**:
    *   Open the Bot GUI.
    *   Go to **Music Services** tab.
    *   Select **Cider** as Active Service.
    *   Paste the Host and Token in the "Cider Config" section.
    *   Click **Save All Music Settings**.

## Running the Bot
- **GUI Mode**: Double-click **`run_gui.bat`**. This launches the Control Panel where you can start/stop the bot and edit settings.
- **Console Mode**: Double-click **`run_bot.bat`**. This runs the bot directly in a terminal window.

## Usage
- **!sr <song name>**: Request a song.
- **!commands**: List available commands.
- **!bot**: Check bot status.

## Troubleshooting
- **Cloudflare/Network Issues**: If the token generator fails, ensure you are not behind a restrictive firewall.
- **"Module not found"**: Re-run `pip install -r requirements.txt`.
