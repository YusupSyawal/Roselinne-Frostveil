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
```

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
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `llama3` | Any pulled Ollama model |
| `MEMORY_MAX_MESSAGES` | `20` | Messages kept per user |
| `COOLDOWN_SECONDS` | `5` | Seconds between `/chat` calls |
| `MAX_TOKENS` | `1000` | Max tokens in AI response |
| `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `TEST_GUILD_ID` | — | Optional: sync commands to one server |

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
