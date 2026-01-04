import re
import aiohttp
import asyncio
import random
import json
import os
from simpleeval import simple_eval

class SimpleContext:
    """Simple context for direct processing without TwitchIO context."""
    def __init__(self, author, args=None, content="", bot=None, channel_name=None):
        self.author = author
        self.args = args if args else []
        self.content = content
        self.bot = bot
        self.channel_name = channel_name

class NightbotEngine:
    def __init__(self):
        self.session = None
        self.counts = {}
        self.counts_file = os.path.join(os.path.dirname(__file__), 'data', 'counts.json')
        self.load_counts()

    async def get_session(self):
        if self.session is None:
            self.session = aiohttp.ClientSession()
        return self.session

    def load_counts(self):
        """Load command counts from file."""
        if os.path.exists(self.counts_file):
            try:
                with open(self.counts_file, 'r', encoding='utf-8') as f:
                    self.counts = json.load(f)
            except Exception as e:
                print(f"Error loading counts: {e}")
                self.counts = {}
        else:
            self.counts = {}
    
    def save_counts(self):
        """Save command counts to file."""
        try:
            with open(self.counts_file, 'w', encoding='utf-8') as f:
                json.dump(self.counts, f, indent=4)
        except Exception as e:
            print(f"Error saving counts: {e}")
    
    def increment_count(self, command_name):
        """Increment the count for a command."""
        # Normalize command name (remove ! prefix if present)
        cmd = command_name.lower()
        if cmd.startswith('!'):
            cmd = cmd[1:]
        
        if cmd not in self.counts:
            self.counts[cmd] = 0
        self.counts[cmd] += 1
        self.save_counts()
        return self.counts[cmd]
    
    def get_count(self, command_name):
        """Get the count for a command."""
        # Normalize command name (remove ! prefix if present)
        cmd = command_name.lower()
        if cmd.startswith('!'):
            cmd = cmd[1:]
        return self.counts.get(cmd, 0)


    async def close(self):
        if self.session:
            await self.session.close()

    async def process(self, template, variables=None):
        """
        Process a template string with both Python formatting and Nightbot variables.
        Intended for use where a full TwitchIO context isn't available (e.g., event responses).
        """
        if variables is None:
            variables = {}
            
        # 1. Python Formatting (e.g. {user})
        try:
            # Only format if there are variables to avoid KeyErrors on unrelated braces
            if variables:
                formatted = template.format(**variables)
            else:
                formatted = template
        except KeyError as e:
            # Fallback if variable missing, log it
            print(f"Missing variable in template processing: {e}")
            formatted = template
        except ValueError as e:
             # Can happen with single braces, e.g. "foo { bar"
             print(f"Value error in template format: {e}")
             formatted = template

        # 2. Nightbot Variable Processing (e.g. $(user))
        if "$(" in formatted:
            # Create a simple context context
            author = variables.get('user', 'Unknown')
            # Extract other potential context vars if available
            ctx = SimpleContext(author=author)
            formatted = await self.process_response(formatted, ctx)
            
        return formatted

    async def process_response(self, response_text, ctx):
        """
        Processes a response string with Nightbot variables.
        ctx needs:
        - author: name of sender
        - args: list of arguments (optional)
        - message: full message content (optional)
        """
        
        # Helper to get args safely
        args = getattr(ctx, 'args', [])
        message_content = getattr(ctx, 'content', '')
        author = ctx.author.name if hasattr(ctx.author, 'name') else str(ctx.author)

        # Process variables - handle nested parentheses properly
        # We'll use a different approach: find $( and match to closing )
        current_text = response_text
        max_loops = 10  # Prevent infinite loops
        
        for _ in range(max_loops):
            # Find the start of a variable
            start_idx = current_text.find('$(')
            if start_idx == -1:
                break  # No more variables
            
            # Find the matching closing parenthesis
            paren_count = 0
            end_idx = -1
            for i in range(start_idx + 1, len(current_text)):
                if current_text[i] == '(':
                    paren_count += 1
                elif current_text[i] == ')':
                    paren_count -= 1
                    if paren_count == 0:
                        end_idx = i
                        break
            
            if end_idx == -1:
                # No matching closing paren, skip this
                break
                
            full_tag = current_text[start_idx:end_idx+1]  # $(cmd args)
            inner_content = current_text[start_idx+2:end_idx]  # cmd args
            
            parts = inner_content.split(' ', 1)
            cmd = parts[0]
            arg = parts[1] if len(parts) > 1 else ""
            
            replacement = full_tag  # Default: don't replace if unknown
            
            if cmd == "user":
                replacement = author
            elif cmd == "touser":
                # If args exist, first arg. Else author.
                # NOTE: In nested context, we refer to original attributes.
                if args:
                    replacement = args[0]
                else:
                    replacement = author
            elif cmd == "query":
                # The rest of the message after the command
                # In twitchio, ctx.content usually includes the command?
                # We'll assume the caller passes only the arguments part if possible
                # Or we strip the command.
                # For now, let's assume 'args' is the list of words.
                replacement = " ".join(args) if args else ""
            
            elif cmd == "count":
                # Get count for the current command
                # ctx should have command_name attribute set by the bot
                command_name = getattr(ctx, 'command_name', None)
                if command_name:
                    count = self.get_count(command_name)
                    replacement = str(count)
                else:
                    replacement = "0"
            
            # Check if cmd is a reference to another command's count (e.g., $(ns), $(nt))
            # This allows cross-command count references
            elif cmd and not arg:  # No arguments, might be a count reference
                # Try to get count for this command name
                count = self.get_count(cmd)
                if count > 0 or cmd in self.counts:  # If it exists or has been used
                    replacement = str(count)
                # Otherwise keep the full_tag as is (will be left in output)
            
            elif cmd == "urlfetch":
                # Async fetch
                try:
                    session = await self.get_session()
                    async with session.get(arg.strip()) as resp:
                        if resp.status == 200:
                            # Limit loading size for safety
                            text = await resp.text()
                            replacement = text[:400] # Cap length
                        else:
                            replacement = f"[Error: {resp.status}]"
                except Exception as e:
                    replacement = f"[Error: {str(e)}]"

            elif cmd == "eval":
                # Python Eval
                try:
                    # WE are using Python eval, not JS.
                    # We inject specific variables for convenience
                    # But Nightbot variables should be resolved by now (inside-out)
                    print(f"[EVAL DEBUG] Evaluating: {arg}")  # Debug
                    result = str(simple_eval(arg, names={"random": random}))
                    print(f"[EVAL DEBUG] Result: {result}")  # Debug
                    replacement = result
                except Exception as e:
                    print(f"[EVAL DEBUG] Error: {e}")  # Debug
                    replacement = f"[Eval Error: {e}]"

            elif cmd == "uptime":
                # Requires ctx to have access to bot/stream info
                # We expect ctx.bot to be the twitchio bot instance
                try:
                    bot = getattr(ctx, 'bot', None)
                    channel_name = getattr(ctx, 'channel_name', None)
                    if bot and channel_name:
                        # Fetch stream info
                        # create task to avoid blocking? process_response is async.
                        # twitchio get_stream usually takes channel ID, or we check cache/API
                        # For simplicity, we assume bot.fetch_streams is available or similar
                        # TwitchIO 2.x: bot.fetch_streams(user_logins=[channel_name])
                        streams = await bot.fetch_streams(user_logins=[channel_name])
                        if streams:
                            uptime = streams[0].uptime
                            # Format uptime
                            # uptime is usually a datetime.timedelta or similar in newer twitchio? 
                            # Wait, twitchio returns Stream object. generic helper:
                            # Actually uptime is current time - started_at
                            # started_at is datetime
                            import datetime
                            now = datetime.datetime.now(datetime.timezone.utc)
                            delta = now - streams[0].started_at
                            
                            # Simple formatting
                            total_seconds = int(delta.total_seconds())
                            hours, remainder = divmod(total_seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            replacement = f"{hours}h {minutes}m {seconds}s"
                        else:
                            replacement = "Stream is offline."
                    else:
                        replacement = "[Error: No context]"
                except Exception as e:
                    replacement = f"[Error fetching uptime: {e}]"
            
            # Replace ONLY the first occurrence of this specific match to avoid loop issues?
            # No, regex search finds the first one. We replace it.
            current_text = current_text.replace(full_tag, str(replacement), 1)

        return current_text
