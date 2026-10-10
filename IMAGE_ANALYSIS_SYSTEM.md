# Image Analysis & Vision System

## Overview

Bot sekarang dapat mendeteksi gambar yang dikirim pengguna dan memberikan komentar serta analisis mendalam tentang gambar tersebut menggunakan AI vision capabilities.

## Features

### 🖼️ Auto-Detection
- Deteksi otomatis gambar dalam Discord messages
- Tanpa perlu mention bot — respons langsung
- Mendukung: JPEG, PNG, GIF, WebP

### 💬 Smart Commentary
- Bot memberikan reaksi/komentar yang witty dan insightful
- Bergaya Roselinne Frostveil (elegant, sarcastic)
- Response dalam Bahasa Indonesia

### 📋 Manual Analysis
- Command `/analyzeimage` untuk upload & analisis gambar
- Bisa menambahkan pertanyaan custom tentang gambar
- Memberikan embed response yang formatted

## Architecture

### Components

1. **ImageHandler** (`utils/image.py`)
   - Download gambar dari URL (Discord CDN)
   - Validasi format & ukuran (max 20MB)
   - Kompresi untuk processing lebih cepat
   - Extract metadata (format, dimensions)

2. **VisionAnalyzer** (`ai/vision_analyzer.py`)
   - Wrapper untuk AI vision capabilities
   - Support: OpenAI GPT-4 Vision, Google Gemini
   - Not supported: Groq, Ollama (text-only)
   - Image-to-text analysis

3. **Message Event Handler** (`events/message.py`)
   - Auto-detect image attachments
   - Async processing dengan typing indicator
   - Store dalam conversation memory

4. **Image Command** (`commands/image.py`)
   - `/analyzeimage` slash command
   - Upload file directly
   - Custom prompt support

## How It Works

### Auto-Detection Flow

```
Discord Message dengan Gambar
    ↓
MessageCog deteksi attachment
    ↓
Download & validate gambar
    ↓
Compress untuk processing
    ↓
VisionAnalyzer analisis
    ↓
Reply dengan komentar
    ↓
Store dalam memory
```

### Command Flow

```
/analyzeimage <file> [prompt]
    ↓
Validate format & provider support
    ↓
Check cooldown
    ↓
Download & process
    ↓
Analysis dengan custom prompt
    ↓
Send formatted embed response
```

## Usage

### Auto-React (No Command Needed)

Cukup upload gambar di channel:
```
User: [uploads image.jpg]
Bot: *Automatically responds with witty comment*
```

### Manual Analysis Command

```
/analyzeimage image:my_photo.jpg prompt:Apa yang bisa Anda lihat di sini?
```

Response akan dalam bentuk embed dengan:
- Title: "Image Analysis: [filename]"
- Description: Analisis detail
- Thumbnail: Preview gambar

## Configuration

### Requirements

Vision hanya berfungsi dengan:
- ✅ **OpenAI** (GPT-4 Vision)
- ✅ **Gemini** (multimodal)
- ❌ **Groq** (text-only)
- ❌ **Ollama** (text-only)

### Environment Variables

```bash
# Ensure AI provider adalah openai atau gemini
AI_PROVIDER=openai
OPENAI_API_KEY=your_key
# atau
AI_PROVIDER=gemini
GEMINI_API_KEY=your_key

# Image handling (optional)
# COOLDOWN_SECONDS=5  # Apply 2x cooldown untuk image commands
```

### .env Configuration

```env
# AI Provider
AI_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4-vision-preview

# atau untuk Gemini
AI_PROVIDER=gemini
GEMINI_API_KEY=AIza...
GEMINI_MODEL=gemini-pro-vision
```

## Technical Details

### Image Processing

**Validation Checks:**
- Format check: supported MIME types
- Size check: max 20MB
- Integrity check: PIL image verify

**Compression:**
- Scale down jika width > 1024px
- Convert ke JPEG dengan quality 75
- Reduce file size untuk faster processing
- Remove alpha channel untuk compatibility

**Timeout Protection:**
- Download timeout: 30 detik
- Analysis timeout: depends on provider

### Dependencies Added

```
Pillow>=10.0.0  # Image processing (PIL)
```

Existing dependencies support vision:
- `openai>=1.30.0` — GPT-4 Vision
- `google-generativeai>=0.3.0` — Gemini Vision

### File Structure

```
utils/
├── image.py          (NEW - image handling)

ai/
├── vision_analyzer.py (NEW - vision analysis)

commands/
├── image.py          (NEW - /analyzeimage command)

events/
└── message.py        (UPDATED - auto-detect images)
```

## Performance

### Latency

- Auto-react: 3-8 seconds (depends on image size)
- Manual command: 4-10 seconds
- Includes: download + compression + analysis

### Resource Usage

- Memory: ~5-10MB per image (after compression)
- Network: Download image once, cached temporarily
- CPU: Compression is lightweight

## Error Handling

### Common Issues

**"Vision not available for this provider"**
```
→ Switch to OpenAI or Gemini
→ Set correct API key in .env
```

**"Image too large"**
```
→ Compress before upload
→ Max size: 20MB
→ System auto-compresses anyway
```

**"Image analysis timed out"**
```
→ Try smaller image
→ Check internet connection
→ Retry with /analyzeimage command
```

**"Unsupported image format"**
```
→ Upload JPEG, PNG, GIF, or WebP
→ Not: BMP, TIFF, etc.
```

## Logging

Monitor di logs untuk vision activity:

```
INFO: Processing image: JPEG (1920x1080)
INFO: Analyzing image from username
DEBUG: Image compressed: 450KB → 85KB
ERROR: Failed to analyze image: timeout
WARNING: Image too large: 25MB
```

Grep untuk: `roselinne.image`, `roselinne.vision`, `roselinne.events.message`

## Security & Privacy

- ✅ Images downloaded temporarily, not stored
- ✅ Only analyze images user explicitly shares
- ✅ No image metadata retained after analysis
- ✅ API calls only via official SDKs
- ✅ Sensitive content handling depends on AI provider's policies

## Future Enhancements

- [ ] Image format conversion (handle more formats)
- [ ] OCR text extraction dari gambar
- [ ] Image classification (detect image type)
- [ ] Emoji reaction based on image content
- [ ] Batch image analysis
- [ ] Image gallery feature (remember analyzed images)
- [ ] Content warning system

## Troubleshooting

### Vision commands not showing up?

```bash
# Make sure extension is loaded
# Check logs for: "Loaded extension: commands.image"

# Resync commands
# Set TEST_GUILD_ID=your_guild_id in .env
# Or restart bot to sync globally
```

### Getting "API key not set" error?

```bash
# Double-check .env file
echo $OPENAI_API_KEY  # or GEMINI_API_KEY

# Make sure values don't have quotes
# ✓ OPENAI_API_KEY=sk-...
# ✗ OPENAI_API_KEY="sk-..."
```

### Image analysis very slow?

```bash
# 1. Resize image before upload (< 2MB ideal)
# 2. Check internet connection
# 3. Monitor provider API status
# 4. Try different image format (JPEG fastest)
```

---

**Status**: ✅ Production Ready  
**Vision Support**: OpenAI (GPT-4V), Gemini (multimodal)  
**Last Updated**: May 21, 2026
