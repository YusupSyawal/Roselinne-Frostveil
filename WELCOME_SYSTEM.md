# Welcome System for New Members

## Overview

Bot sekarang akan secara otomatis menyambut anggota baru yang join ke server dengan pesan yang elegant dan sesuai dengan personality Roselinne Frostveil.

## Features

### 🎉 Auto-Welcome
- Deteksi otomatis ketika member baru join
- Kirim welcome message ke general channel (atau channel pertama yang tersedia)
- Tidak perlu setup khusus — langsung berfungsi
- Elegant embed dengan member info

### 💬 Witty Greetings
- Multiple welcome messages dengan personality yang berbeda
- Setiap welcome random dari beberapa pilihan
- Styled sesuai karakter Roselinne (elegant, sarcastic, formal)

### 📊 Member Information
- Nama dan mention member
- Account age
- Total guild members
- Member avatar
- Timestamp welcome

### 🛠️ Admin Commands
- `/welcome @member` - Manual welcome untuk specific member
- `/welcomechannel #channel` - Set custom welcome channel
- Admin-only permissions

## How It Works

### Auto-Detection Flow

```
Member Join Event
    ↓
Check if bot (skip if yes)
    ↓
Find general/welcome/introductions channel
    ↓
Check bot has permission to send
    ↓
Generate welcome embed
    ↓
Send to channel
    ↓
Log the event
```

### Welcome Message Structure

```
╔════════════════════════════════╗
║          ✨ Welcome            ║
╠════════════════════════════════╣
║ Ah, a new soul arrives...      ║
║                                ║
║ Member: @username (name)       ║
║ Account Age: X days old        ║
║ Guild Members: 42              ║
╠════════════════════════════════╣
║ Welcomed at • Guild Name       ║
╚════════════════════════════════╝
```

## Usage

### Automatic (No Configuration Needed)

```
1. Member joins server
2. Bot automatically sends welcome message in general channel
3. Member sees witty greeting
```

### Manual Welcome Command

**Usage:**
```
/welcome @member_name
```

**Example:**
```
/welcome @JohnDoe
```

### Set Welcome Channel

**Usage:**
```
/welcomechannel #channel_name
```

**Example:**
```
/welcomechannel #introductions
```

**Reset to auto-detect:**
```
/welcomechannel
```

## Configuration

### Auto-Channel Detection Priority

Bot akan mencari welcome channel dalam urutan berikut:
1. **#general** - Most common default channel
2. **#welcome** - Dedicated welcome channel
3. **#introductions** - Member intro channel
4. **First available text channel** - Fallback

Bot hanya akan post jika memiliki permission `send_messages` di channel tersebut.

### Requirements

- Bot harus memiliki `Send Messages` permission di target channel
- Bot harus memiliki `Read Messages` permission
- Member intent harus enabled (usually default)

### Environment Setup

Tidak perlu setup environment variable khusus. System auto-detect channel.

## Customization

### Welcome Messages

Edit `events/member.py` untuk custom welcome greetings. Cari `welcome_messages` list:

```python
welcome_messages = [
    f"Ah, a new soul arrives...",
    f"Welcome, {member.mention}...",
    # Add your own messages here
]
```

### Embed Styling

Edit `_generate_welcome_message()` method untuk customize:
- Title
- Description
- Fields
- Colors
- Footer

### Account Age Format

Automatic format berdasarkan account age:
- Just created
- 1 day old
- X days old
- X months old
- X years old

## Troubleshooting

### "Welcome message tidak muncul"

**Check 1: Bot permissions**
```
→ Verify bot has "Send Messages" in general/target channel
→ Check "Read Messages" permission
```

**Check 2: Member intent**
```
→ Ensure "Guild Members" intent is enabled
→ In Discord Portal → Bot → Privileged Gateway Intents
```

**Check 3: Logs**
```
→ Check bot logs for: "Welcome message sent"
→ Or error messages: "Cannot send message", "permission denied"
```

### "Welcome message di wrong channel"

```
→ Use /welcomechannel #correct_channel
→ Or bot auto-detects general/welcome/introductions
```

### "Bot tidak join event trigger"

```
→ Make sure bot has proper intents
→ Restart bot after permission changes
→ Check logs: grep "Member.*joined"
```

## Event Logging

Monitor di logs untuk member join events:

```
INFO: Member 'username' (ID: 123) joined Guild Name
INFO: Welcome message sent to general for username
ERROR: Cannot send message in general (permission denied)
WARNING: No general channel found in Guild Name
```

Grep untuk: `roselinne.events.member`

## Performance

- **Instant**: Welcome message sent as soon as member joins
- **Non-blocking**: Doesn't affect other bot operations
- **Reliable**: Graceful error handling if send fails

## Security & Privacy

- ✅ No personal data stored (member avatar from Discord)
- ✅ Member info publicly displayed on Discord anyway
- ✅ Only greets legitimate server members
- ✅ Respects channel permissions

## Future Enhancements

- [ ] Database storage of welcome preferences per server
- [ ] Custom welcome messages per server
- [ ] Role assignment on join
- [ ] Welcome DM option
- [ ] Join statistics/tracking
- [ ] Verification system before welcome
- [ ] Multiple language welcome messages

## File Structure

```
events/
├── ready.py      (existing)
├── message.py    (existing)
└── member.py     (NEW - on_member_join handler)

commands/
└── welcome.py    (NEW - /welcome, /welcomechannel commands)

main.py          (UPDATED - load member & welcome cogs)
```

## Admin Commands Reference

### /welcome @member
Send welcome message for specific member (requires manage_guild)

### /welcomechannel [#channel]
Set or reset welcome channel (requires manage_guild)

Both commands are ephemeral and only visible to command executor.

## Discord Permissions Required

Bot needs these permissions in target channel:
- ✅ View Channel / Read Messages
- ✅ Send Messages
- ✅ Embed Links (for embed formatting)

Optional (nice to have):
- Add Reactions (for future enhancements)

---

**Status**: ✅ Production Ready  
**Auto-Detection**: Enabled (no config needed)  
**Last Updated**: May 21, 2026
