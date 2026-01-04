"""
Cider (Apple Music) integration for managing song queue via Cider client API.
"""
import requests
import re
from config import CIDER_TOKEN, CIDER_HOST

class CiderManager:
    """Manages Cider Client API interactions."""
    
    def __init__(self):
        """Initialize Cider client."""
        self.host = CIDER_HOST
        self.token = str(CIDER_TOKEN).strip() if CIDER_TOKEN else None
        
        # Try sending both headers to covers all Cider versions
        self.headers = {
            "apptoken": self.token,
            "apitoken": self.token
        } if self.token else {}

    def connect(self):
        """Check connection to Cider."""
        try:
            # Try a lightweight endpoint, e.g. playback status
            r = requests.get(f"{self.host}/api/v1/playback/active", headers=self.headers, timeout=2)
            if r.status_code == 200:
                print("✓ Cider client connected")
                return True
            elif r.status_code == 401:
                print("⚠️ Cider authentication failed. Check CIDER_TOKEN.")
                return False
            else:
                print(f"⚠️ Cider returned status {r.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            print("⚠️ Could not connect to Cider. Is it running?")
            return False
        except Exception as e:
            print(f"⚠️ Cider connection error: {e}")
            return False

    def extract_track_id(self, input_str):
        """
        Extract Apple Music Song ID from URL.
        """
        input_str = input_str.strip()
        
        # https://music.apple.com/us/album/song-name/123456?i=789012
        # 'i' param is the song ID in an album context
        i_match = re.search(r'[?&]i=(\d+)', input_str)
        if i_match:
            return i_match.group(1)
            
        # https://music.apple.com/us/song/name/123456
        song_match = re.search(r'/song/[^/]+/(\d+)', input_str)
        if song_match:
            return song_match.group(1)
            
        # Check if it's just an ID
        if re.match(r'^\d+$', input_str):
            return input_str
            
        return None

    def get_track_info(self, track_id):
        """
        Get track info using Cider's Apple Music API proxy.
        GET /api/v1/amapi/catalog/{storefront}/songs/{id}
        """
        try:
            # Default to 'us' storefront if unknown, or maybe we can fetch it.
            storefront = 'us' 
            url = f"{self.host}/api/v1/amapi/catalog/{storefront}/songs/{track_id}"
            r = requests.get(url, headers=self.headers, timeout=5)
            
            if r.status_code == 200:
                data = r.json()
                # AMAPI response structure: {'data': [{'attributes': {...}}]}
                if data.get('data') and len(data['data']) > 0:
                    attrs = data['data'][0]['attributes']
                    return {
                        'name': attrs.get('name'),
                        'artist': attrs.get('artistName'),
                        'album': attrs.get('albumName'),
                        'url': attrs.get('url'),
                        'image_url': attrs.get('artwork', {}).get('url', '').replace('{w}', '300').replace('{h}', '300')
                    }
            else:
                print(f"⚠️ Cider get_track_info failed: {r.status_code} {r.text}")
                
            # Fallback: Scrape Apple Music Website
            return self.scrape_track_info(track_id)
            
        except Exception as e:
            print(f"Error fetching Cider track info: {e}")
            return self.scrape_track_info(track_id)

    def scrape_track_info(self, track_id):
        """Fallback: Scrape metadata from Apple Music public URL."""
        try:
            # Construct a generic URL - 'us' storefront is usually fine for metadata
            url = f"https://music.apple.com/us/song/{track_id}"
            
            # Use a real user agent to avoid being blocked
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            print(f"🕵️ Scraping metadata from {url}...")
            r = requests.get(url, headers=headers, timeout=5)
            r.encoding = 'utf-8' # Force UTF-8 to avoid encoding artifacts
            
            if r.status_code == 200:
                import html as html_lib # Import here to avoid top-level dirtying if preferred, or rely on top
                
                page_content = r.text
                
                # Extract Title and Artist from <title> tag
                # Common formats:
                # "Song Name by Artist on Apple Music"
                # "Song Name - Song by Artist - Apple Music"
                # "Album Name by Artist on Apple Music"
                
                title_match = re.search(r'<title>(.*?)</title>', page_content)
                if title_match:
                    raw_title = title_match.group(1)
                    full_title = html_lib.unescape(raw_title)
                    # 1. Strip invisible characters (like LRM \u200e) and whitespace
                    full_title = full_title.strip().strip('\u200e\u200f')
                    
                    # 2. Remove "Apple Music" suffix (handling NBSP \xa0 and various dashes)
                    # Pattern: [dash/pipe] [space] Apple [space] Music [end]
                    full_title = re.sub(r'\s*[-–—|]\s*Apple[\s\xa0]*Music\s*$', '', full_title, flags=re.IGNORECASE)
                    
                    # 3. Clean " - Song by " pattern to just " by "
                    full_title = re.sub(r'\s*[-–—|]\s*Song\s+by\s+', ' by ', full_title, flags=re.IGNORECASE)
                    
                    # 4. Remove other end-of-string suffixes if they remain
                    full_title = re.sub(r'\s*[-–—|]\s*(Single|EP)\s*$', '', full_title, flags=re.IGNORECASE)
                    if " by " in full_title:
                        parts = full_title.rsplit(" by ", 1)
                        track_name = parts[0].strip()
                        artist_name = parts[1].strip()
                        
                        # Clean leading/trailing non-alphanumeric if messy
                        # (Optional, but fixes 'â' type artifacts if they are at edges)
                    else:
                        track_name = full_title.strip()
                        artist_name = "Unknown"
                        
                    return {
                        'name': track_name,
                        'artist': artist_name,
                        'album': 'Apple Music',
                        'url': url,
                        'image_url': '' 
                    }
            
            print(f"⚠️ Scraping failed: {r.status_code}")
            return None
        except Exception as e:
            print(f"Error scraping metadata: {e}")
            return None

    def search_track(self, query):
        """
        Search for a track using Cider's Apple Music API proxy.
        GET /api/v1/amapi/catalog/{storefront}/search?types=songs&term=...&limit=1
        """
        try:
            storefront = 'us'
            url = f"{self.host}/api/v1/amapi/catalog/{storefront}/search"
            params = {
                'types': 'songs',
                'term': query,
                'limit': 1
            }
            r = requests.get(url, headers=self.headers, params=params, timeout=5)
            
            if r.status_code == 200:
                data = r.json()
                # Structure: results -> songs -> data -> [ { id: ..., attributes: ... } ]
                songs = data.get('results', {}).get('songs', {}).get('data', [])
                if songs:
                    song = songs[0]
                    track_id = song['id']
                    attrs = song['attributes']
                    track_info = {
                        'id': track_id,
                        'name': attrs.get('name'),
                        'artist': attrs.get('artistName'),
                        'url': attrs.get('url')
                    }
                    return True, "SEARCH_SUCCESS", track_info
            else:
                 print(f"⚠️ Cider search failed: {r.status_code} {r.text}")
            
            # Fallback to iTunes Search API (Public)
            return self.search_itunes(query)
            
        except Exception as e:
            print(f"Cider search error: {e}")
            # Try iTunes fallback even on exception
            return self.search_itunes(query)

    def search_itunes(self, query):
        """Fallback: Search using public iTunes API."""
        try:
             url = "https://itunes.apple.com/search"
             params = {
                 "term": query,
                 "media": "music",
                 "entity": "song",
                 "limit": 1
             }
             print(f"🌍 Searching iTunes API for: {query}")
             r = requests.get(url, params=params, timeout=5)
             
             if r.status_code == 200:
                 data = r.json()
                 if data.get("resultCount", 0) > 0:
                     track = data["results"][0]
                     track_id = str(track.get("trackId"))
                     
                     return True, "SEARCH_SUCCESS", {
                         "id": track_id,
                         "name": track.get("trackName"),
                         "artist": track.get("artistName"),
                         "url": track.get("trackViewUrl")
                     }
             
             print("⚠️ iTunes search found no results.")
             return False, "SEARCH_NO_RESULTS", None
             
        except Exception as e:
             print(f"iTunes search error: {e}")
             return False, "SEARCH_ERROR", None

    def add_to_queue(self, input_str):
        """
        Add track to Cider queue (Play Next).
        """
        try:
            track_id = self.extract_track_id(input_str)
            was_search = False
            track_info = None

            if not track_id:
                # Search mode
                print(f"Searching Cider for: {input_str}")
                success, msg, info = self.search_track(input_str)
                if not success:
                    return False, msg, None
                track_id = info['id']
                track_info = info
                was_search = True
            else:
                # Direct ID mode - fetch info for display
                track_info = self.get_track_info(track_id)
            
            # Try multiple endpoints for play-next
            payload = {
                "id": track_id,
                "type": "songs"
            }
            
            # List of candidate endpoints to try
            endpoints = [
                "/api/v1/playback/play-next",# Prioritizing this as it gave 403 (means route exists)
                "/play-next",                # Root
                "/api/v1/play-next",         # API v1 prefix
                "/api/v1/playback/queue"     # Queue namespace
            ]
            
            for path in endpoints:
                 url = f"{self.host}{path}"
                 try:
                     print(f"Trying Cider endpoint: {path}")
                     r = requests.post(url, headers=self.headers, json=payload, timeout=2)
                     if r.status_code in [200, 204]:
                         print(f"✓ Success using {path}")
                         return True, "QUEUE_SUCCESS", track_info
                     elif r.status_code != 404:
                         # If it's not 404, it might be the right endpoint but wrong payload/auth
                         print(f"⚠️ Endpoint {path} error: {r.status_code} {r.text}")
                 except: pass
            
            print(f"❌ All Cider add endpoints failed.")
            return False, "QUEUE_ADD_FAILED", None

        except requests.exceptions.ConnectionError:
            return False, "CIDER_NOT_RUNNING", None
        except Exception as e:
            print(f"Cider add exception: {e}")
            return False, "QUEUE_ADD_FAILED", None

    def get_current_track(self):
        """Get currently playing track information."""
        try:
            # Try multiple endpoints
            endpoints = [
                "/api/v1/playback/now-playing",
                "/api/v1/playback/active"
            ]
            
            data = None
            for path in endpoints:
                try:
                    r = requests.get(f"{self.host}{path}", headers=self.headers, timeout=2)
                    if r.status_code == 200:
                        data = r.json()
                        break
                except: continue
            
            if not data:
                return False, "CIDER_NOT_PLAYING", None

            # Cider usually returns object directly or wrapped
            # Check for 'info' or 'artwork' keys common in Cider API
            info = data.get('info', data)
            if not info or 'name' not in info:
                 return False, "CIDER_NO_TRACK", None
            
            # Format to match SpotifyManager output
            track_info = {
                'track_name': info.get('name', 'Unknown'),
                'artist': info.get('artistName', 'Unknown'),
                'album': info.get('albumName', 'Unknown'),
                'url': info.get('url', ''),
                'image_url': info.get('artwork', {}).get('url', '').replace('{w}', '300').replace('{h}', '300'),
                'is_playing': data.get('isPlaying', True)
            }
            
            return True, "TRACK_INFO_SUCCESS", track_info

        except Exception as e:
            print(f"Cider get_current_track error: {e}")
            return False, "TRACK_INFO_ERROR", None
