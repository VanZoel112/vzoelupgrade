#!/usr/bin/env python3
"""
Local Configuration Override
Copy this file to config_local.py and fill in your credentials

IMPORTANT: config_local.py is gitignored for security!
Never commit sensitive credentials to public repository!
"""

# ==============================================
# TELEGRAM BOT CREDENTIALS
# ==============================================

# Bot Token from @BotFather
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# API credentials from https://my.telegram.org
API_ID = 0
API_HASH = "YOUR_API_HASH_HERE"

# ==============================================
# ASSISTANT ACCOUNT (for voice chat streaming)
# ==============================================

# Generate using: .gensession command in bot PM or run genstring.py
# Leave empty ("") to disable streaming mode (download mode only)
STRING_SESSION = ""

# ==============================================
# OWNER & DEVELOPERS
# ==============================================

OWNER_ID = 0  # Your Telegram User ID

# Developer IDs (can use . prefix commands)
DEVELOPER_IDS = [
    0,  # Add your user ID here
]
