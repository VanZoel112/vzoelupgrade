# VBot Python 🎵

**Vzoel Robot** - Comprehensive Telegram Music Bot converted from Node.js to Python

## Features ✨

### 🎵 Music System
- **yt-dlp Integration** - High-quality music download
- **Inline Controls** - Play/Pause/Next/Previous buttons
- **Smart Search** - YouTube music search
- **Download Management** - Auto cleanup, file size limits

### 🔐 Authorization System
- **Multi-level Access** - `/` admin, `.` developer, `#` public commands
- **Permission Caching** - Efficient admin verification
- **Role-based Commands** - Different access levels

### 🔒 Lock System
- **Auto-delete** - Locked users' messages automatically deleted
- **Persistent Storage** - Lock data saved to JSON
- **GitHub Sync** - Auto backup to repository

### 💎 Premium Emoji System
- **Auto-convert** - Standard to premium emojis for Telegram Premium users
- **Fallback Support** - Graceful degradation for non-premium
- **Customizable Mappings** - Add your own emoji conversions

### 🏷️ Tag System
- **Progressive Tagging** - Edit message instead of spam
- **Cancellable** - `/ctag` to stop ongoing tags
- **Rate Limited** - Configurable delays between edits

### 👋 Welcome System
- **Auto-welcome** - Greet new members
- **Toggle per Group** - Enable/disable per chat
- **Custom Messages** - Personalized welcome text
- **Placeholder Support** - `{first_name}`, `{username}`, etc.

### 📁 GitHub Integration
- **Auto Backup** - Push data to GitHub repository
- **Queue System** - Background sync processing
- **Structure Creation** - Auto-create repo structure

### 🤫 Privacy System
- **Silent Commands** - Execute commands privately
- **Auto-delete** - Remove command messages in groups
- **Private Response** - Send responses to user's DM

## Installation 🚀

### 1. Clone Repository
```bash
git clone https://github.com/VanZoel112/vbot-python.git
cd vbot-python
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Configuration
```bash
cp .env.example .env
# Edit .env with your credentials
```

### 4. Run Bot
```bash
python main.py
```

## Configuration ⚙️

### Required Environment Variables
```env
# Telegram API (from https://my.telegram.org)
TELEGRAM_API_ID=your_api_id
TELEGRAM_API_HASH=your_api_hash
TELEGRAM_BOT_TOKEN=your_bot_token

# Authorization
OWNER_ID=your_user_id
DEVELOPER_IDS=dev_id1,dev_id2
ADMIN_CHAT_IDS=chat_id1,chat_id2
```

### Optional Features
```env
# GitHub Integration
GITHUB_TOKEN=your_github_token
GITHUB_REPOSITORY=username/repo_name

# Feature Toggles
ENABLE_MUSIC=true
ENABLE_LOCK_SYSTEM=true
ENABLE_PREMIUM_EMOJI=true
ENABLE_TAG_SYSTEM=true
ENABLE_WELCOME_SYSTEM=true
ENABLE_GITHUB_SYNC=true
ENABLE_PRIVACY_SYSTEM=true

# Tag system tuning
TAG_BATCH_SIZE=5
TAG_DELAY=2.0
```

## Commands 📝

### Admin Commands (`/`)
- `/play <song>` - Play music from YouTube
- `/lock <user>` - Lock user (auto-delete messages)
- `/unlock <user_id>` - Unlock user
- `/t [batch] <message>` atau `/t` (reply) - Tag semua anggota secara bertahap (alias: `.t`, `+t`)
- `/c` - Hentikan proses tag massal (alias: `.c`, `+c`)

### Developer Commands (`.`)
- `.stats` - Show bot statistics
- `.setwelcome <message>` - Set welcome message
- `.welcome on/off` - Toggle welcome system
- `.privacy` - Toggle privacy mode
- `.t [batch] <message>` atau `.t` (reply) - Alias admin untuk `/t`

### Public Commands (`#`)
- `#help` - Show help message
- `#rules` - Show group rules
- `#session` - Generate session string

## Architecture 🏗️

```
vbot-python/
├── main.py              # Main application
├── config.py            # Configuration management
├── requirements.txt     # Dependencies
├── .env.example        # Environment template
├── core/               # Core functionality
│   ├── auth_manager.py    # Permission system
│   ├── emoji_manager.py   # Premium emoji conversion
│   └── music_manager.py   # Music system
├── modules/            # Feature modules
│   ├── lock_manager.py    # Lock system
│   ├── tag_manager.py     # Tag system
│   ├── welcome_manager.py # Welcome system
│   ├── github_sync.py     # GitHub integration
│   └── privacy_manager.py # Privacy system
├── data/               # Data storage
├── downloads/          # Music downloads
└── logs/              # Application logs
```

## Conversion from Node.js ♻️

This bot was **completely converted from Node.js to Python** with the following improvements:

- ✅ **Better Performance** - Python async/await efficiency
- ✅ **Type Safety** - Type hints and dataclasses
- ✅ **Error Handling** - Comprehensive exception management
- ✅ **Modularity** - Clean separation of concerns
- ✅ **Scalability** - Easy to extend and maintain

## Contributing 🤝

1. Fork the repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License 📄

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support 💬

- **GitHub Issues** - Bug reports and feature requests
- **Telegram** - @VanZoel112

---

**Made with ❤️ by VanZoel112**

*Powered by Python 🐍 | Enhanced with Claude Code 🤖*