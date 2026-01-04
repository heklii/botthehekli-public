"""
Spotify integration for managing song queue.
Handles authentication and adding tracks to the Spotify queue.
"""
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SPOTIFY_SCOPES
import re
import os
import requests

class SpotifyManager:
    """Manages Spotify API interactions."""
    
    def __init__(self, api_timeout=30):
        """Initialize Spotify client with OAuth."""
        self.sp = None
        self.playlist_url = None  # Will be loaded from settings
        self.api_timeout = api_timeout
        self.connect()
    
    def connect(self):
        """Attempt to connect to Spotify."""
        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            print("Spotify credentials not found.")
            return

        try:
            auth_manager = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=SPOTIFY_SCOPES,
                cache_path='.spotify_cache'
            )
            # Add timeout to requests
            self.sp = spotipy.Spotify(
                auth_manager=auth_manager,
                requests_timeout=self.api_timeout
            )
            print("✓ Spotify authentication successful")
        except Exception as e:
            print(f"Failed to authenticate with Spotify: {e}")

    def extract_track_id(self, spotify_input):
        """
        Extract Spotify track ID from various input formats.
        """
        # Remove any whitespace
        spotify_input = spotify_input.strip()
        
        # Pattern for full URLs
        url_pattern = r'open\.spotify\.com/track/([a-zA-Z0-9]+)'
        url_match = re.search(url_pattern, spotify_input)
        if url_match:
            return url_match.group(1)
        
        # Pattern for URIs
        uri_pattern = r'spotify:track:([a-zA-Z0-9]+)'
        uri_match = re.search(uri_pattern, spotify_input)
        if uri_match:
            return uri_match.group(1)
        
        # Check if it's already a track ID (alphanumeric, typically 22 chars)
        if re.match(r'^[a-zA-Z0-9]{15,}$', spotify_input):
            return spotify_input
        
        return None
    
    def get_track_info(self, track_id):
        """Get track information from Spotify."""
        if not self.sp: return None
        try:
            track = self.sp.track(track_id)
            return {
                'name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'uri': track['uri'],
                'album_art': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'url': track['external_urls']['spotify']
            }
        except requests.exceptions.ReadTimeout:
            print(f"Timeout getting track info for {track_id}")
            return None
        except Exception as e:
            print(f"Error getting track info: {e}")
            return None
    
    def search_track(self, query):
        """Search for a track on Spotify with improved scoring."""
        if not self.sp: return False, "SPOTIFY_NOT_CONNECTED", None
        try:
            # Fetch top 5 results
            results = self.sp.search(q=query, type='track', limit=5)
            
            if not results or not results.get('tracks', {}).get('items'):
                return False, "SEARCH_NO_RESULTS", None
            
            items = results['tracks']['items']
            best_match = None
            best_score = -1
            
            # Helper to strip non-alphanumeric
            def normalize(s):
                return re.sub(r'[^a-z0-9]', '', s.lower())
            
            query_norm = normalize(query)
            query_lower = query.lower()
            
            for track in items:
                score = 0
                track_name = track['name']
                artist_name = track['artists'][0]['name'] # Primary artist
                popularity = track['popularity']
                
                # Base score from popularity (0-100)
                # Reduced weight of popularity so matches matter more
                score += popularity * 0.5 
                
                track_norm = normalize(track_name)
                
                # Exact Name Match (Normalized)
                if query_norm == track_norm:
                    score += 100
                # Partial Name Match
                elif query_norm in track_norm or track_norm in query_norm:
                    score += 50
                    
                # Artist Match
                artist_norm = normalize(artist_name)
                if artist_norm in query_norm:
                    score += 50
                    
                # Combined "Artist - Title" match check (Normalized)
                # This handles "Artist - Title" or "Title - Artist"
                combined_norm = normalize(artist_name + track_name)
                if query_norm == combined_norm:
                     score += 200 # Perfect combo match
                elif query_norm in combined_norm or combined_norm in query_norm:
                    score += 150 # Strong combo match
                
                if score > best_score:
                    best_score = score
                    best_match = track
            
            if not best_match:
                best_match = items[0]

            track_name = best_match['name']
            artist_name = ', '.join([artist['name'] for artist in best_match['artists']])
            track_uri = best_match['uri']
            
            return True, "SEARCH_SUCCESS", track_uri
        
        except requests.exceptions.ReadTimeout:
            return False, "SEARCH_TIMEOUT", None
        except Exception as e:
            return False, "SEARCH_ERROR", None
    
    def add_to_queue(self, track_input, playlist_url=None):
        """Add a track to the Spotify queue and optionally to a playlist."""
        if not self.sp: return False, "SPOTIFY_NOT_CONNECTED", None
        try:
            # First, try to extract track ID from URL/URI
            track_id = self.extract_track_id(track_input)
            
            # If no track ID found, treat as search query
            if not track_id:
                print(f"No Spotify link detected, searching for: {track_input}")
                success, message, track_uri = self.search_track(track_input)
                
                if not success:
                    return False, message, None
                
                # Extract track ID from the URI we got from search
                track_id = track_uri.split(':')[-1]
                was_search = True
            else:
                was_search = False
                track_uri = f"spotify:track:{track_id}"
            
            # Get track info
            track_info = self.get_track_info(track_id)
            if not track_info:
                return False, "TRACK_INFO_FAILED", None
            
            # Add to queue
            self.sp.add_to_queue(track_id)
            
            # Add to playlist if URL provided
            playlist_msg = ""
            if playlist_url:
                playlist_success, playlist_result = self.add_to_playlist(track_uri, playlist_url)
                if playlist_success:
                    playlist_msg = " and saved to playlist"
                else:
                    print(f"⚠️ Could not add to playlist: {playlist_result}")
            
            return True, "QUEUE_SUCCESS", track_info
            
        except requests.exceptions.ReadTimeout:
            return False, "QUEUE_TIMEOUT", None
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 404:
                return False, "NO_DEVICE", None
            elif e.http_status == 403:
                return False, "PREMIUM_REQUIRED", None
            else:
                return False, "SPOTIFY_API_ERROR", None
        except Exception as e:
            return False, "QUEUE_ADD_FAILED", None

    def get_current_track(self):
        """Get currently playing track information."""
        if not self.sp: return False, "SPOTIFY_NOT_CONNECTED", None
        try:
            current = self.sp.current_playback()
            
            if not current or not current.get('item'):
                return False, "NO_TRACK_PLAYING", None
            
            track = current['item']
            
            track_info = {
                'track_name': track['name'],
                'artist': ', '.join([artist['name'] for artist in track['artists']]),
                'album': track['album']['name'],
                'url': track['external_urls']['spotify'],
                'image_url': track['album']['images'][0]['url'] if track['album']['images'] else None,
                'is_playing': current['is_playing']
            }
            
            return True, "TRACK_INFO_SUCCESS", track_info
            
        except Exception as e:
            return False, "TRACK_INFO_ERROR", None

    def skip_track(self):
        """Skip to the next track."""
        if not self.sp: return False, "SPOTIFY_NOT_CONNECTED"
        try:
            self.sp.next_track()
            return True, "SKIP_SUCCESS"
        except Exception as e:
            return False, "SKIP_FAILED"
    
    def add_to_playlist(self, track_uri, playlist_url):
        """Add a track to a Spotify playlist."""
        if not self.sp:
            return False, "Spotify not connected"
        
        if not playlist_url:
            return False, "No playlist URL configured"
        
        try:
            # Extract playlist ID from URL
            playlist_id = None
            
            # Remove any query parameters first (e.g., ?si=xxx)
            clean_url = playlist_url.split('?')[0]
            
            # Pattern for full playlist URLs: open.spotify.com/playlist/{id}
            url_pattern = r'open\.spotify\.com/playlist/([a-zA-Z0-9]+)'
            url_match = re.search(url_pattern, clean_url)
            if url_match:
                playlist_id = url_match.group(1)
            
            # Pattern for playlist URIs: spotify:playlist:{id}
            if not playlist_id:
                uri_pattern = r'spotify:playlist:([a-zA-Z0-9]+)'
                uri_match = re.search(uri_pattern, clean_url)
                if uri_match:
                    playlist_id = uri_match.group(1)
            
            # Check if it's already just a playlist ID (22 characters alphanumeric)
            if not playlist_id and re.match(r'^[a-zA-Z0-9]{22}$', clean_url):
                playlist_id = clean_url
            
            # If still no match, assume it's a partial playlist ID
            if not playlist_id:
                # Just use the cleaned input as the ID
                playlist_id = clean_url
            
            if not playlist_id:
                return False, "Invalid playlist URL or ID"
            
            print(f"Adding track {track_uri} to playlist {playlist_id}")
            
            # Add track to playlist
            self.sp.playlist_add_items(playlist_id, [track_uri])
            return True, f"Added to playlist"
            
        except requests.exceptions.ReadTimeout:
            return False, "Playlist add timed out"
        except spotipy.exceptions.SpotifyException as e:
            if e.http_status == 403:
                return False, "No permission to modify this playlist"
            elif e.http_status == 404:
                return False, "Playlist not found"
            else:
                return False, f"Spotify error: {e.msg}"
        except Exception as e:
            return False, f"Failed to add to playlist: {str(e)}"
