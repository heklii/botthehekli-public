# Setting Up Your Commands Page (Cloudflare Pages + Gist)

This bot can automatically sync your commands to a public webpage hosted on Cloudflare Pages, powered by a GitHub Gist backend.

## 1. Create a GitHub Gist
The bot stores your commands in a JSON file on GitHub Gist, which serves as a database for your website.

1.  Go to [gist.github.com](https://gist.github.com/).
2.  Create a new Gist.
    *   **Filename**: `commands.json`
    *   **Content**: `{}` (Just empty curly braces).
3.  Click **Create secret gist** (or public, doesn't matter much if the ID is known, but secret is cleaner).
4.  **Copy the Gist ID** from the URL (the long string of numbers/letters at the end).
    *   Example: `https://gist.github.com/user/`**`8f7d8f...`**
5.  **Generate a GitHub Token**:
    *   Go to GitHub Settings -> Developer settings -> Personal access tokens -> Tokens (classic).
    *   Generate new token (classic).
    *   **Scopes**: Check `gist`.
    *   Copy the token.
6.  **Enter Credentials in Bot GUI**:
    *   Open `run_gui.bat`.
    *   Go to **Settings**.
    *   Under "Website Sync", enter your **GitHub Token** and **Gist ID**.
    *   Click **Force Sync Now** (make sure the bot is running!).

## 2. Deploy to Cloudflare Pages
You will host the lightweight frontend (HTML/JS) on Cloudflare Pages for free. This folder is included as `commands_page/`.

1.  **Configure `app.js`**:
    *   Open `commands_page/app.js` in a text editor.
    *   Find the line: `const GIST_URL = "";`
    *   **Get your Gist Raw URL**:
        - Go to your Gist on GitHub.
        - Click the "Raw" button on `commands.json`.
        - Copy the URL (Result looks like: `https://gist.githubusercontent.com/.../raw/commands.json`).
        - **Tip**: Remove the long commit hash from the URL (the part between your username and `/raw/`) to ensure it always points to the latest version.
    *   Paste it into `GIST_URL`:
        ```javascript
        const GIST_URL = "https://gist.githubusercontent.com/username/id/raw/commands.json";
        ```
    *   Save `app.js`.

2.  **Deploy**:
    *   Log in to [Cloudflare Dashboard](https://dash.cloudflare.com/).
    *   Go to **Workers & Pages** -> **Create Application** -> **Pages**.
    *   **Upload Assets**: Select **Upload Assets** and choose the `commands_page` folder.
    *   Deploy!

3.  **Update Your Bot Command**:
    *   In the Bot GUI -> Commands tab, add or edit `!commands`.
    *   Response: `Check out my commands here: <YOUR_CLOUDFLARE_PAGES_URL>`

## Automatic Updates
Once set up, every time you add or edit a command in the Bot GUI, it will automatically update the Gist. Your Cloudflare Page (which reads from that Gist) will reflect the changes instantly (or on next refresh).
