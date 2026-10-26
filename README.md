# Discord Linux Screen Streaming Bot

A foreground-run Python application where **screen1** captures a Linux desktop as **video only**, encodes H.264 with FFmpeg, sends RTMP, and serves an HLS player for **screen2**. An allowlisted Discord bot can control the capture process and post the player link.

The capture process remains stopped until an authorized `/start` command is used. `/stop` ends it. The bot does not capture audio, run hidden, or start automatically at login.

> A public player exposes the desktop to anyone who can reach its URL. Close private windows and notifications before starting. Do not publish a viewing URL you intend to keep private.

## Hosting limitation

The screen-streaming process must run on the Linux machine whose logged-in desktop you want to capture. Render cannot see your personal X11 or Wayland desktop, so deploying the streamer there will not capture your screen. The included Render service is a separate, lightweight health page only; it does not capture a desktop, run the Discord bot, or keep another Render service awake.

Run the streamer on screen1's desktop host and use the included `keep_live.py` only when you need a separate Render web service with `/` and `/health`.

## Participants and streaming modes

- **screen1** is the normal Discord user who runs the Linux capture client. In HLS mode, screen1 publishes the video from that desktop.
- **screen2** is the normal Discord user who watches. In HLS mode, screen2 opens the player URL in a browser.
- `SCREEN1_DISCORD_USER_ID` and `SCREEN2_DISCORD_USER_ID` identify those users for bot-command permissions. They are numeric user IDs, not credentials; they do not log either user into Discord.
- `DISCORD_BOT_TOKEN` logs in only the separate bot application. The bot does not join calls or transmit native Discord video.

### Native Discord Go Live (manual)

For screen sharing inside Discord itself, screen1 and screen2 each sign in normally through Discord's official client. Both manually join the same voice channel. screen1 chooses **Share Your Screen / Go Live** in the client and selects the desktop or application; screen2 watches the stream in that call. The users must have permission to join and stream in that channel. See Discord's [Go Live and Screen Share guide](https://support.discord.com/hc/en-us/articles/360040816151-Go-Live-and-Screen-Share).

These steps are manual. This project does not log in either participant, join the call, press Go Live, or send its FFmpeg video into Discord. Do not use personal-account tokens or a self-bot to automate this; Discord [prohibits automating normal user accounts](https://support.discord.com/hc/en-us/articles/115002192352-Automated-User-Accounts-Self-Bots).

### RTMP/HLS player (alternative)

In this mode, screen1 runs the Linux capture client and publishes video to the configured RTMP ingest and local HLS output. screen2 watches the HLS player URL in a browser. An authorized user runs the bot's `/share` command to post `PUBLIC_VIEW_URL` in a Discord text channel. The bot posts a link; it does not transmit the native Discord video stream. The HLS link is public to anyone who can reach it.

## Requirements

- Linux desktop session using X11 or Wayland
- Python 3.10+
- FFmpeg with an H.264 encoder (`libx264` is the default)
- For Wayland: FFmpeg built with PipeWire input support, PipeWire, and a working desktop screen-capture portal
- An RTMP ingest endpoint and stream key
- Optional Discord bot token, screen1/screen2 Discord user IDs, and optional additional bot-admin IDs

### Install system packages

Install Python and FFmpeg using your distribution:

```bash
# Ubuntu / Debian
sudo apt install python3 python3-venv ffmpeg

# Fedora
sudo dnf install python3 ffmpeg

# Arch Linux
sudo pacman -S python ffmpeg
```

On NixOS, make `python3`, `ffmpeg`, and the relevant desktop/PipeWire packages available to the shell or system. For Wayland, confirm the FFmpeg package was built with PipeWire support.

Check the FFmpeg features before configuring the app:

```bash
ffmpeg -encoders | grep -E 'libx264|h264_'
ffmpeg -demuxers | grep -E 'x11grab|pipewire'
```

The application repeats these checks before starting capture and reports missing features on the player page and at `/health`.

## Install and configure

```bash
cd discord-linux-streamer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` on screen1's Linux host. For RTMP/HLS mode, set `RTMP_INGEST_URL` and `STREAM_KEY`. The stream key is a secret: keep `.env` out of version control and do not paste the key into chat. To enable bot controls, also set `DISCORD_BOT_TOKEN` and `SCREEN1_DISCORD_USER_ID`; set `SCREEN2_DISCORD_USER_ID` to identify the viewer.

### Environment variables

These settings have different purposes:

- `DISCORD_BOT_TOKEN` authenticates the bot application to Discord; it is not screen1's or screen2's account token.
- `SCREEN1_DISCORD_USER_ID` and `SCREEN2_DISCORD_USER_ID` identify the participants for permission checks. They are not login credentials.
- `STREAM_KEY` authenticates the outbound RTMP ingest; it is appended to `RTMP_INGEST_URL`. It is not a Discord or personal-account token.

Secrets are read from environment variables (or a local `.env` file). Do not commit `.env`, paste secrets into chat, or expose them in a public status page.

### Authentication methods actually implemented

- **Discord bot:** `discord.py` logs in as the bot using `DISCORD_BOT_TOKEN`. It receives slash-command interactions and checks the caller against configured Discord user IDs.
- **screen1/screen2:** each is a normal Discord user who signs in independently using Discord's official client. This app stores no personal account tokens and does not log these users in.
- **RTMP:** FFmpeg uses `STREAM_KEY` only for RTMP ingest authorization.
- **Not implemented:** bot-driven voice calls or native Discord video/screen-share transmission; Discord OAuth login for screen1 or screen2; or authentication for HLS viewers.

| Variable | Default | Required / purpose |
| --- | --- | --- |
| `APP_HOST` | `127.0.0.1` | HTTP server bind address. Use `0.0.0.0` only when intentionally exposing it through a firewall or reverse proxy. |
| `APP_PORT` | `8000` | HTTP server port for the desktop streamer. |
| `PUBLIC_VIEW_URL` | empty | Public player page URL shared by `/share`. |
| `HLS_PLAYBACK_URL` | empty | Optional external HLS playlist URL. Blank uses this app's `/hls/stream.m3u8`. |
| `CAPTURE_BACKEND` | `auto` | `auto`, `x11`, or `pipewire`; automatic selection follows the current desktop session. |
| `X11_DISPLAY` | `$DISPLAY` | Optional X11 display override. |
| `X11_OFFSET` | `+0,0` | X11 capture origin. |
| `PIPEWIRE_SOURCE` | `0` | PipeWire capture node/source identifier. |
| `VIDEO_WIDTH` | `1920` | Output width in pixels. |
| `VIDEO_HEIGHT` | `1080` | Output height in pixels. |
| `VIDEO_FPS` | `30` | Capture/output frame rate. |
| `VIDEO_BITRATE` | `4500k` | H.264 target bitrate. |
| `VIDEO_ENCODER` | `libx264` | H.264 encoder available in the installed FFmpeg build. |
| `RTMP_INGEST_URL` | `rtmp://localhost/live` | RTMP provider ingest/application URL, without the stream key. Set to your provider's URL before starting. |
| `STREAM_KEY` | empty | RTMP credential; set this before `/start`. Keep it private. |
| `HLS_OUTPUT_DIR` | `./var/hls` | Local directory for generated HLS playlist and segments. |
| `RECONNECT_BASE_SECONDS` | `2` | Initial FFmpeg reconnect delay. |
| `RECONNECT_MAX_SECONDS` | `30` | Maximum FFmpeg reconnect delay. |
| `SCREEN1_DISCORD_USER_ID` | empty | screen1's numeric Discord user ID. May run `/start`, `/stop`, `/status`, and `/share`. Required for bot control unless an additional admin is configured. |
| `SCREEN2_DISCORD_USER_ID` | empty | screen2's numeric Discord user ID. May run `/status` and `/share`, but cannot start or stop screen1's capture. |
| `DISCORD_BOT_TOKEN` | empty | Optional bot-application credential. Leave blank to disable the bot; it is not a personal account token. |
| `DISCORD_ALLOWED_USER_IDS` | empty | Optional comma-separated additional bot admins. These IDs retain full command access. |
| `DISCORD_ALLOWED_GUILD_IDS` | empty | Optional comma-separated server IDs limiting where bot commands are available. |

`SCREEN1_DISCORD_USER_ID` and `SCREEN2_DISCORD_USER_ID` must identify different Discord users. These IDs are labels/permission selectors, not authentication tokens. `keep_live.py` is independent of all streamer settings. Render provides its `PORT` environment variable; no Discord or RTMP credentials are needed by that service.

The local HLS playlist is at `/hls/stream.m3u8`. `HLS_PLAYBACK_URL` is sent to every player page, so treat it as public if set. Configure HTTPS and public routing yourself, for example with a reverse proxy or a secure tunnel. Do not expose the control bot token or RTMP stream key through a public web server.

## X11

Use `CAPTURE_BACKEND=x11` or leave it at `auto` in an X11 session. The app uses `DISPLAY`, captures the configured dimensions at the configured frame rate, and applies scaling/padding to the output dimensions. If the active display is smaller than the selected capture region, reduce `VIDEO_WIDTH`/`VIDEO_HEIGHT` or set an appropriate `X11_OFFSET`.

## Wayland / PipeWire

Set `CAPTURE_BACKEND=pipewire`. Run the app from the logged-in desktop session so it can access the user's PipeWire socket. `PIPEWIRE_SOURCE` selects the PipeWire capture node (default `0`). Create/approve a desktop capture session with the compositor's screen-share portal and set its node identifier here; the application does not automate the portal prompt. A raw PipeWire node ID is only usable if the compositor has made that capture source available to the session.

This path requires an FFmpeg build whose `-demuxers` output includes `pipewire`. Many stock FFmpeg packages do not include a compatible PipeWire video input even when PipeWire is installed; the app reports this separately from a missing `ffmpeg` executable and does not silently fall back to X11.

## Discord setup

1. Create a bot in the Discord Developer Portal and enable its bot user.
2. Invite it to the server with permission to use slash commands and send messages.
3. Copy the bot token into `DISCORD_BOT_TOKEN` in the local `.env` file. Never commit or share it.
4. Enable Developer Mode in Discord and set screen1's numeric user ID as `SCREEN1_DISCORD_USER_ID`.
5. Set screen2's numeric user ID as `SCREEN2_DISCORD_USER_ID`.
6. Optionally set `DISCORD_ALLOWED_USER_IDS` for additional users who need full bot-admin access, and `DISCORD_ALLOWED_GUILD_IDS` to restrict bot commands to specific servers.

Commands:

- `/start` — screen1 starts its foreground desktop capture and RTMP/HLS publishing
- `/stop` — screen1 stops capture
- `/status` — screen1 or screen2 checks stream state, encoder, and reconnect count
- `/share` — screen1 or screen2 asks the bot to post `PUBLIC_VIEW_URL` in the current channel

screen1 can run all four commands; screen2 can run `/status` and `/share` only. IDs in `DISCORD_ALLOWED_USER_IDS` remain full-access bot admins for backwards compatibility. If a bot token is set without a screen1 ID or any admin ID, startup reports a configuration error. With no bot token, the local player still runs and the app logs that Discord is disabled.

## Run

Start it from the Linux desktop session:

```bash
source .venv/bin/activate
python -m screen_streamer
```

Open `http://127.0.0.1:8000/` locally. In HLS mode, screen1 publishes and screen2 watches this player URL; `/share` lets the bot post `PUBLIC_VIEW_URL` into Discord. The HLS player updates its state every few seconds. The health endpoint is `http://127.0.0.1:8000/health`; detailed status is at `/api/status`. To make it publicly viewable, configure `APP_HOST`, firewall/reverse-proxy routing, HTTPS, and `PUBLIC_VIEW_URL` deliberately.

The app does not install a system service or configure automatic startup. Stop it with Ctrl+C after stopping the stream. If an RTMP write stalls for 15 seconds, FFmpeg exits and the supervisor retries with exponential backoff.

## Tests

From the project root, install the full requirements and run:

```bash
python -m unittest discover -s tests -v
```

## Render keep-alive web service

The repository includes a `render.yaml` Blueprint for one standalone web service. Connect the GitHub repository to Render and deploy the Blueprint, or create a Python web service manually with these commands:

| Render service | Build command | Start command |
| --- | --- | --- |
| `discord-streamer-keep-live` | `pip install -r requirements-keep-live.txt` | `python keep_live.py` |

The service binds to `0.0.0.0` and reads Render's `PORT` variable (defaulting to `8000` locally). It does not read or log tokens, stream keys, Discord settings, or screen-capture settings. Its health check is `/health`.

Run it locally:

```bash
cd discord-linux-streamer
python -m pip install -r requirements-keep-live.txt
PORT=8000 python keep_live.py
```

Test both endpoints locally:

```bash
curl -i http://127.0.0.1:8000/
curl -i http://127.0.0.1:8000/health
```

The root page displays “Service is running”; `/health` returns HTTP 200 with `{"status":"ok"}`. After deployment, replace `127.0.0.1:8000` with the Render service URL to test the same paths. This health service is not a workaround for Render's lack of access to your desktop.

The desktop streamer itself is **not a working Render screen-capture service**. Its local commands are `python -m pip install -r requirements.txt` and `python -m screen_streamer`, and it must run inside the target desktop session. Deploying that process on Render would not grant it access to your computer's X11/Wayland screen.

## Troubleshooting

- **FFmpeg missing:** install it from your distribution and ensure `ffmpeg` is on `PATH`.
- **Encoder missing:** choose an encoder reported by `ffmpeg -encoders`; `VIDEO_ENCODER` must be an H.264 encoder available in your FFmpeg build.
- **X11 display unavailable:** run from the graphical X11 session; check `echo "$DISPLAY"` and `X11_DISPLAY`.
- **PipeWire input missing:** verify `ffmpeg -demuxers | grep pipewire`, that PipeWire is running, and that the desktop portal granted screen capture.
- **RTMP connection failure:** verify the ingest URL, stream key, firewall, and provider dashboard. The app retries temporary FFmpeg exits with exponential backoff.
- **Player has no picture:** use `/health` and `/api/status`, confirm RTMP ingest is accepted, check that `/hls/stream.m3u8` exists, and confirm the public proxy serves `.m3u8` and `.ts` files without caching the playlist.
- **Logs:** inspect `var/logs/streamer.log` on the Linux host. Keys and bot tokens are redacted from displayed FFmpeg errors.

## Safety and network notes

- Capture is video-only (`-an`); there is no microphone or system audio input.
- There is no unauthenticated HTTP start/stop endpoint. Stream control is via allowlisted Discord users.
- The player, health, and status endpoints are read-only. If exposed publicly, assume anyone can view them and the video.
- The RTMP key and Discord token must be supplied as environment variables on the Linux host, not embedded in code.
