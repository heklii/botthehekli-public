@echo off
TITLE Generate Twitch Tokens
echo ==========================================
echo      Twitch Token Generator
echo ==========================================
echo.
echo This script will open your browser to authorize.
echo Make sure you have CLIENT_ID and CLIENT_SECRET in your .env file!
echo.
python generate_token.py
pause
