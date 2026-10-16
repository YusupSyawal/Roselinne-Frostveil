# ❄️ Roselinne Frostveil — Discord AI Bot

> *"I assist — reluctantly at times, but thoroughly."*

A modern, modular Discord AI chatbot built with Python 3.11+, `discord.py` 2.x, and your choice of AI provider (OpenAI, Groq, or Ollama). Named and voiced as **Roselinne Frostveil** — an elegant, slightly sardonic noble of the Winter Court.

---

## ✨ Features

| Feature | Details |
|---|---|
| **AI Chat** | `/chat` with full conversation memory per user per server |
| **Persistent Memory** | SQLite-backed, survives bot restarts |
| **Multi-provider AI** | OpenAI · Groq (free tier) · Ollama (local) |
| **Slash Commands** | `/chat` `/resetmemory` `/ping` `/help` `/personality` |
| **Mini Music** | `/music play` and queue/playback controls for one YouTube video |
| **Cooldown System** | Configurable per-user anti-spam |
| **Typing Indicator** | Shows "typing…" while AI thinks |
| **Frost/silver-blue Embeds** | Themed Discord embeds throughout |
| **Auto-reconnect** | discord.py handles reconnect natively |
| **Docker Support** | Single-command deploy anywhere |
| **Modular Cog System** | Easy to add new commands |

---

## 📁 Project Structure

```
roselinne-frostveil/
│
├── main.py                  ← Entry point; loads all cogs
├── .env                     ← Your secrets (never commit this)
├── .env.example             ← Template for .env
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
│
├── config/
│   ├── settings.py          ← All config in one place
│   └── personality.txt      ← Roselinne's character — edit freely
│
├── commands/
│   ├── chat.py              ← /chat  /resetmemory  /personality
│   ├── music.py             ← /music playback and queue controls
│   ├── ping.py              ← /ping
│   └── help.py              ← /help
│
├── events/
│   ├── ready.py             ← on_ready, on_guild_join, reconnect logs
│   └── message.py           ← on_message, error handlers
│
├── ai/
│   ├── ai_client.py         ← Multi-provider AI client (OpenAI/Groq/Ollama)
│   ├── memory.py            ← SQLite conversation memory
│   └── prompt_builder.py    ← Builds the messages list for the AI
│
├── utils/
│   ├── logger.py            ← Coloured console + rotating file logger
│   └── cooldown.py          ← Per-user cooldown manager
│
└── data/
    ├── memory.db            ← SQLite database (auto-created)
    └── memory/              ← Reserved for future JSON exports
```

---

## 🚀 Quick Start (Windows / Linux / macOS)

### 1. Prerequisites

- **Python 3.11+** — [python.org/downloads](https://www.python.org/downloads/)
- **Git** (optional, for cloning)
- **VS Code** (recommended) with the Python extension

Verify your Python version:
```bash
python --version
# or on Linux/macOS:
python3 --version
```

---

### 2. Clone / Download the Project

```bash
git clone https://github.com/yourname/roselinne-frostveil.git
cd roselinne-frostveil
```

Or download the ZIP and extract it.

---

### 3. Create a Virtual Environment

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

---

### 4. Install Dependencies

```bash
pip install -r requirements.txt
```

---

### 5. Configure Discord Developer Portal

#### Create a Bot Application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → give it a name (e.g. "Roselinne Frostveil")
3. Go to the **Bot** tab on the left sidebar
4. Click **Add Bot** → confirm

#### Get Your Bot Token

1. Under the **Bot** tab, click **Reset Token** → copy and save it
2. This is your `DISCORD_BOT_TOKEN`

#### Enable Privileged Intents

Still under the **Bot** tab, scroll to **Privileged Gateway Intents** and enable:
- ✅ **Message Content Intent** (required for reading messages)

#### Get Your Client ID

1. Go to the **OAuth2** → **General** tab
2. Copy the **Client ID** — this is your `DISCORD_CLIENT_ID`

#### Invite the Bot to Your Server

1. Go to **OAuth2** → **URL Generator**
2. Under **Scopes**, check:
   - ✅ `bot`
   - ✅ `applications.commands`
3. Under **Bot Permissions**, check:
   - ✅ Send Messages
   - ✅ Use Slash Commands
   - ✅ Embed Links
   - ✅ Read Message History
   - ✅ Connect
   - ✅ Speak
4. Copy the generated URL and open it in your browser
5. Select your server and click **Authorize**

---

### 6. Set Up Environment Variables

Copy the template:
```bash
# Windows
copy .env.example .env

# Linux / macOS
cp .env.example .env
```

Edit `.env` with your values:

```env
DISCORD_BOT_TOKEN=your_token_here
DISCORD_CLIENT_ID=your_client_id_here

AI_PROVIDER=openai
OPENAI_API_KEY=your_openai_key_here
OPENAI_MODEL=gpt-4o-mini
```

**Optional — faster command sync during development:**
```env
TEST_GUILD_ID=your_test_server_id_here
```
*(Right-click your server icon in Discord → Copy Server ID. Enable Developer Mode first: User Settings → Advanced.)*

---

### 7. Run the Bot

**From the terminal:**
```bash
python main.py
```

**From VS Code:**
1. Open the project folder in VS Code
2. Press `F5` (uses `.vscode/launch.json` which is already configured)

You should see:
```
──────────────────────────────────────────────────────
  Roselinne Frostveil is awake.
  Logged in as : Roselinne Frostveil#1234 (ID: ...)
  Guilds       : 1
  Latency      : 42 ms
──────────────────────────────────────────────────────
```

### Diagnosing duplicate AI replies

Message-based AI replies use one workflow registry shared by the bot instance.
The registry claims a Discord message ID before generation and keeps the
completed state long enough to suppress a repeated gateway/listener event.
Only the message workflow owner calls `message.reply`; generators, image
analysis, verification, and formatting return data instead of sending it.

Diagnostic records in `logs/roselinne.log` include `message_id`,
`workflow_id`, `process_id`, and `instance_id` without logging tokens or the
full message content. For a manual check, send one mention and search the log
for that message ID: there should be one `AI_GENERATION_START` and one
`RESPONSE_SEND_SUCCESS`. A second event should produce `DUPLICATE_SUPPRESSED`.

The process lock prevents two Roselinne processes that share the same
`data/roselinne.lock` path. Check the startup log for one
`BOT_GATEWAY_READY` record and verify that no second process/container is
running. Discord does not provide an idempotency key for a reply, so a network
failure after a send begins remains an inherently ambiguous delivery outcome;
the workflow deliberately does not retry that send or issue a fallback.

Logging defaults to `INFO` on the console and `DEBUG` in the rotating file log.
Set `LOG_LEVEL=DEBUG` when live console tracing is needed, or adjust
`LOG_FILE_LEVEL` to control diagnostic detail retained in `logs/roselinne.log`.

Slash commands are loaded in `setup_hook()` and synced before the gateway
becomes ready. With `TEST_GUILD_ID`, the complete local tree is copied and
synced to that guild for fast testing. Without it, commands are synced
globally and Discord propagation can take time. Startup logs report the local
command names, sync scope, synced names, and a post-sync Discord command
comparison; in particular, look for `has_usage=true` in
`APPLICATION_COMMAND_TREE_LOCAL`, `APPLICATION_COMMAND_SYNC`, and
`APPLICATION_COMMAND_REMOTE`.

---

## 🎵 Mini Music

Mini Music is independent from the AI provider and remains available when AI is
off. The supported commands are:

- `/music play url:<URL>` — queue one YouTube video.
- `/music queue` and `/music nowplaying` — inspect playback.
- `/music pause`, `/music resume`, `/music skip`, `/music stop`, `/music leave`.

Install the **FFmpeg executable** separately and ensure it is available on
`PATH`, or set `FFMPEG_PATH` in `.env` to its executable path. The bot requires
**Connect** and **Speak** permissions in the target voice channel. Queues are
kept in memory per guild and are discarded when the process stops; an idle
connection leaves after approximately five minutes when no track is queued.

YouTube playback uses `yt-dlp` to obtain a temporary audio stream and does not
download or permanently store music. Only single video URLs are accepted;
playlists are rejected. Spotify URLs are validated, but a legitimate Spotify
resolver is not configured yet, so the bot reports that limitation instead of
pretending to play Spotify audio or bypassing DRM/access restrictions.

Audio is decoded by FFmpeg to the PCM format expected by `discord.py`, then
encoded once by Discord's Opus encoder. The default is 128 kbps, full-band
music mode, with FEC enabled for resilience; the effective bitrate is capped
to the voice channel's advertised bitrate when available. Configure
`MUSIC_OPUS_BITRATE`, `MUSIC_OPUS_FEC`, and `MUSIC_EXPECTED_PACKET_LOSS` only
within the documented safe ranges. No gain, bass boost, treble boost,
aggressive compression, or loudness filter is enabled by default, which
avoids clipping and preserves natural dynamics. Discord's actual voice bitrate
and Opus path—not the source URL's nominal quality—remain the final limit.

## 🛡️ AI Control and Moderator Mode

Roselinne keeps Discord connectivity, member events, moderation-related
commands, welcome/leave messages, `/ping`, and `/help` working when AI is off.
AI requests are disabled by default until a server administrator uses:

- `/ai_on` — enable AI responses for the current server
- `/ai_off` — disable chat, mentions, and image analysis before any AI API call
- `/ai_status` — check the current state

The commands require **Manage Server** (or Administrator) permission. State is
stored locally in `data/runtime_state.json`; if that file is missing or cannot
be read, AI remains OFF. Use `/welcomechannel` and `/leavechannel` to configure
member event channels. The optional `WELCOME_CHANNEL_ID` and
`LEAVE_CHANNEL_ID` environment variables provide fallback channel IDs.

### Run as a separate Windows process

From PowerShell, outside the VS Code debugger:

```powershell
Set-Location C:\path\to\roselinne-frostveil
.\venv\Scripts\python.exe .\main.py
```

Keep the terminal open, or use Windows Task Scheduler to start it at logon:

1. Open **Task Scheduler** → **Create Task**.
2. On **General**, choose **Run whether user is logged on or not** if desired.
3. On **Triggers**, add **At log on** (or **At startup**).
4. On **Actions**, choose **Start a program**:
   - **Program:** `C:\path\to\roselinne-frostveil\venv\Scripts\python.exe`
   - **Arguments:** `C:\path\to\roselinne-frostveil\main.py`
   - **Start in:** `C:\path\to\roselinne-frostveil`
5. On **Conditions**, disable the AC-power restriction if appropriate.
6. Save the task and test **Run**. Review the bot log if startup fails.

Use the virtual-environment interpreter directly; do not rely on a different
Python selected by VS Code or on a global `python` command.

---

## 🤖 AI Provider Setup

### OpenAI (default)

1. Get an API key at [platform.openai.com](https://platform.openai.com)
2. Set in `.env`:
```env
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini   # or gpt-4o for higher quality
```

### Groq (fast & free tier)

1. Sign up at [console.groq.com](https://console.groq.com)
2. Create an API key
3. Set in `.env`:
```env
AI_PROVIDER=groq
GROQ_API_KEY=gsk_...
GROQ_MODEL=openai/gpt-oss-120b
GROQ_VISION_MODEL=qwen/qwen3.8-27b
```

`GROQ_MODEL` remains the text-chat model. `GROQ_VISION_MODEL` is used only for
image and meme analysis. The documented Groq vision model is
`qwen/qwen3.8-27b`; verify the active model list before selecting another
preview model.

### Ollama (local, no API key)

1. Install Ollama: [ollama.ai](https://ollama.ai)
2. Pull a model: `ollama pull llama3`
3. Set in `.env`:
```env
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3
```

---

## 🛠️ Slash Commands

| Command | Description |
|---|---|
| `/chat <message>` | Send a message to Roselinne |
| `/resetmemory` | Erase your conversation history |
| `/personality` | View bot info and your chat stats |
| `/ping` | Check bot latency |
| `/help` | Show all commands |

---

## 🎭 Customising the Personality

Edit `config/personality.txt` and restart the bot. No code changes needed. The file is loaded fresh on each bot start.

---

## 🐋 Docker Deployment

### Build and run locally:
```bash
docker compose up --build -d
```

### View logs:
```bash
docker compose logs -f
```

### Stop:
```bash
docker compose down
```

---

## 🖥️ Deploying to a VPS (Linux)

### Option A — Direct Python

```bash
# 1. SSH into your server
ssh user@your-server-ip

# 2. Install Python 3.11+
sudo apt update && sudo apt install python3.11 python3.11-venv git -y

# 3. Clone & setup
git clone https://github.com/yourname/roselinne-frostveil.git
cd roselinne-frostveil
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env   # fill in your values

# 4. Run as a systemd service (auto-restart on crash/reboot)
sudo nano /etc/systemd/system/roselinne.service
```

Paste this into the service file:
```ini
[Unit]
Description=Roselinne Frostveil Discord Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/home/youruser/roselinne-frostveil
EnvironmentFile=/home/youruser/roselinne-frostveil/.env
ExecStart=/home/youruser/roselinne-frostveil/venv/bin/python main.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable roselinne
sudo systemctl start roselinne
sudo systemctl status roselinne
```

### Option B — Docker on VPS

```bash
# Install Docker
curl -fsSL https://get.docker.com | sh

# Clone, configure, deploy
git clone https://github.com/yourname/roselinne-frostveil.git
cd roselinne-frostveil
cp .env.example .env && nano .env
docker compose up --build -d
```

---

## 🔧 Configuration Reference

| Variable | Default | Description |
|---|---|---|
| `DISCORD_BOT_TOKEN` | — | **Required.** Your bot token. |
| `DISCORD_CLIENT_ID` | — | **Required.** Your application client ID. |
| `AI_PROVIDER` | `openai` | `openai` / `groq` / `ollama` |
| `OPENAI_API_KEY` | — | Required if `AI_PROVIDER=openai` |
| `OPENAI_MODEL` | `gpt-4o-mini` | Any OpenAI chat model |
| `GROQ_API_KEY` | — | Required if `AI_PROVIDER=groq` |
| `GROQ_MODEL` | `openai/gpt-oss-120b` | Any Groq model |
| `GROQ_VISION_MODEL` | `qwen/qwen3.8-27b` | Groq multimodal image model |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Any pulled Ollama model |
| `MEMORY_MAX_MESSAGES` | `20` | Messages kept per user |
| `COOLDOWN_SECONDS` | `5` | Seconds between `/chat` calls |
| `MAX_TOKENS` | `1000` | Max tokens in AI response |
| `LOG_LEVEL` | `INFO` | Console level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `LOG_FILE_LEVEL` | `DEBUG` | Rotating file level: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `TEST_GUILD_ID` | — | Optional: sync commands to one server |

### Token and usage monitoring

`/usage` shows local AI request and token accounting for the current server.
Choose the `section` option as `summary`, `limits`, or `reset`; Discord
application commands cannot expose both a standalone `/usage` command and a
`/usage` subcommand group with the same name. The reset option requires
administrator/server-owner permission and `confirm:true`.

Usage data is stored in `data/usage.db`, separate from the conversation
database at `data/memory.db`. Provider usage metadata is recorded as actual
when returned by OpenAI, Groq, Gemini, or Ollama. Otherwise a dependency-free
local estimate is stored and labelled as estimated. Failed provider attempts
count as requests but do not create output tokens. The feature does not query
provider quota endpoints and does not claim local statistics are official
provider usage.

---

## 📝 Adding New Commands

1. Create `commands/mycommand.py`:
```python
import discord
from discord import app_commands
from discord.ext import commands

class MyCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="mycommand", description="Does something.")
    async def mycommand(self, interaction: discord.Interaction):
        await interaction.response.send_message("Hello!")

async def setup(bot):
    await bot.add_cog(MyCog(bot))
```

2. Register it in `main.py` under `extensions`:
```python
"commands.mycommand",
```

3. Restart the bot.

---

## 📄 License

MIT — do as you please. A small acknowledgement is appreciated but not required.

## Credits
- Original Creator & Developer: [@YusupJawier](https://github.com/YusupJawier)

# Roselinne-Frostveil
