# VBot Branding Assets

This directory stores visual branding assets that can be shared directly from the bot. Place the official branding image provided by the project owner in this folder using the exact filename `vbot_branding.png`.

For music playback you can optionally provide a separate logo image. The bot reads the `MUSIC_LOGO_FILE_PATH` environment variable and, when set to a valid file or HTTP URL, sends that artwork with queue updates. Upload your preferred music logo to Telegram (or host it elsewhere), copy its file ID or URL, and update the configuration value accordingly.

The bot will automatically attempt to serve this image when users request branding information. If the image is missing, the bot falls back to a textual notice so chats are never left without a response.


## Adding or Updating the Image

1. Save the branding artwork as `vbot_branding.png`.
2. Copy the file into this directory: `assets/branding/vbot_branding.png`.
3. Restart the bot (or redeploy) if necessary so the new asset is available.

The PNG format is recommended to preserve quality and transparency. Ensure the artwork matches the official styling shared with the project.
