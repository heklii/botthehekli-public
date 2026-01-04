# Default Commands & Variables

## Variables

These variables can be used in your custom command responses.

### 1. Dynamic Variables (Global)
These work in **any** custom command or response.

| Variable | Description | Example |
| :--- | :--- | :--- |
| `$(user)` | The name of the user who triggered the command. | `Hello $(user)!` |
| `$(touser)` | The first argument provided (target user). Defaults to sender if no arg. | `Go check out $(touser)!` |
| `$(query)` | All arguments passed to the command. | `You said: $(query)` |
| `$(count)` | The number of times the command has been used. | `Used $(count) times.` |
| `$(eval <code>)` | Executes Python code. (Safe subset + `random`). | `$(eval random.randint(1,10))` |
| `$(urlfetch <url>)` | Fetches text from a URL (max 400 chars). | `$(urlfetch https://api.my.com/joke)` |
| `$(uptime)` | Shows how long the stream has been live. | `Stream uptime: $(uptime)` |
| `$(<cmd_name>)`| Shows the count of *another* command if referenced. | `Deaths: $(death_counter)` |

### 2. Context-Specific Variables
These are available **only** in specific command responses (e.g., Music).

**For `!song`, `!sr`, `!csr` (Success):**
| Variable | Description |
| :--- | :--- |
| `{track_name}` | Name of the track. |
| `{artist}` | Artist name. |
| `{album}` | Album name. |
| `{url}` | Link to the track. |
| `{user}` | Name of the requesting user. |
| `{position}` | Position in queue (only for `!sr` success). |
| `{query}` | The original search query (only for `!sr`). |

**For Errors:**
| Variable | Description |
| :--- | :--- |
| `{error_code}` | Technical reason for failure. |
| `{error_message}`| Human-readable error message. |
| `{user}` | Name of the user. |

## Default Commands

| Command | Aliases | Description | Permission |
| :--- | :--- | :--- | :--- |
| `!sr` | `!request`, `!songrequest` | Request a song on Spotify. | Everyone |
| `!csr` | `!cider` | Request a song on Apple Music (via Cider). | Everyone |
| `!song` | | Display the currently playing song. (Spotify Only) | Everyone |
| `!clip` | | Create a clip of the stream (last 30s). | Everyone |
| `!commands` | | Link to the commands page. | Everyone |

## Music Integration
- **Spotify**: Fully supported for requests (`!sr`) and current song (`!song`).
- **Cider (Apple Music)**: Supported for requests (`!csr`) and current song (`!song` if set as active service).
- **LastFM**: Not currently implemented.
