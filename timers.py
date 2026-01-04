import json
import asyncio
import time
import os
from config import TIMERS_FILE

class TimerManager:
    def __init__(self, bot):
        self.bot = bot
        self.timers = []
        self.line_count = 0
        self.last_run_time = {} # timer_name -> timestamp
        self.running = False
        self.load_timers()

    def load_timers(self):
        if os.path.exists(TIMERS_FILE):
            with open(TIMERS_FILE, 'r') as f:
                self.timers = json.load(f)
        # Structure: [{"name": "socials", "message": "Follow me!", "interval": 15 (min), "lines": 2}]

    def save_timers(self):
        with open(TIMERS_FILE, 'w') as f:
            json.dump(self.timers, f, indent=4)

    def track_line(self):
        self.line_count += 1
        # Potentially check timers here? Or in background loop?
        # Background loop is better for "time" based, but "lines" based is event driven.
        # Hybrid: Loop checks time, but verifies lines.

    async def start(self):
        self.running = True
        while self.running:
            await asyncio.sleep(60) # Check every minute
            await self.check_timers()

    async def check_timers(self):
        now = time.time()
        for timer in self.timers:
            name = timer.get("name")
            interval_min = timer.get("interval", 15)
            required_lines = timer.get("lines", 2)
            message = timer.get("message")
            
            last_run = self.last_run_time.get(name, 0)
            
            # Check Time
            if now - last_run >= (interval_min * 60):
                # Check Lines (Logic: Since last run? Or just global activity?)
                # Nightbot logic: "Minimum lines since last timer"
                # Implementation: We need to store line_count AT last_run
                # This is a bit complex for a simple loop.
                # Simplification: We just use global line count? No, that doesn't work.
                # We need "last_run_line_count".
                
                last_run_line_count = self.last_run_time.get(f"{name}_lines", 0)
                if (self.line_count - last_run_line_count) >= required_lines:
                    # FIRE!
                    await self.broadcast(message)
                    self.last_run_time[name] = now
                    self.last_run_time[f"{name}_lines"] = self.line_count

    async def broadcast(self, message_template):
        # We need to send to the channel.
        # bot.connected_channels might be empty if just started?
        # We assume initial_channels[0]
        # Or iterate all channels (for multi-channel bot)
        for channel in self.bot.connected_channels:
             # We can use the engine here too! 
             # But timers usually don't have a user context (sender).
             # We pass a dummy context?
             try:
                 # Fake context object? 
                 # Or just send raw text if no variables?
                 # If variables exist, we need a context.
                 # Let's create a minimal context.
                 # class MockCtx: pass...
                 # For now, just send raw text to be safe.
                 await channel.send(message_template)
             except Exception as e:
                 print(f"Timer Error: {e}")

    def add_timer(self, name, message, interval=15, lines=2):
        self.timers.append({
            "name": name,
            "message": message,
            "interval": int(interval),
            "lines": int(lines)
        })
        self.save_timers()

    def delete_timer(self, name):
        self.timers = [t for t in self.timers if t["name"] != name]
        self.save_timers()
