# VBot Command Structure & Permission System

## Permission Levels

### 1. `+` Prefix - OWNER/DEVELOPER Only
Commands untuk management bot dan user permissions.

**Commands:**
- `+setwelcome <message>` - Set welcome message
- `+setwelcome on` - Enable welcome
- `+setwelcome off` - Disable welcome
- `+add @username` atau `+add` (reply) - Give user permission to use `/` commands
- `+del @username` atau `+del` (reply) - Remove user permission

**Permission:** Hanya OWNER_ID dan DEVELOPER_IDS

### 2. `/` Prefix - ADMIN + OWNER/DEV
Commands untuk group management.

**Commands:**
- `/tagall` (reply) atau `/tagall <message>` - Tag all members
- `/cancel` - Stop ongoing tagall
- `/pm @username` atau `/pm` (reply) - Promote to admin (requires admin rights)
- `/dm @username` atau `/dm` (reply) - Demote from admin
- `/lock @username` atau `/lock` (reply) - Auto-delete user messages
- `/unlock @username` atau `/unlock` (reply) - Remove lock
- `/locklist` - Show locked users
- `/help` - Show help (available to all)

**Permission:**
- Group admins (auto-detected)
- Users given permission via `+add`
- OWNER/DEVELOPER

**Feature:** Visible di entry message (slash command suggestions)

### 3. `.` Prefix - ALL USERS
Public commands yang bisa digunakan semua orang.

**Commands:**
- `.play <song>` - Play music
- `.pause` - Pause music
- `.resume` - Resume music
- `.stop` - Stop music
- `.queue` - Show queue
- `.gensession` - Generate session string (PM only)

**Permission:** Semua user

**Feature:** Displayed as inline buttons

## Database Structure

```json
{
  "authorized_users": [
    "123456789",           // Global permission
    "-1001234:987654321"   // Chat-specific permission
  ],
  "locks": {
    "-1001234": [987654321, 123456789]  // Locked users per chat
  },
  "welcome": {
    "-1001234": {
      "enabled": true,
      "message": "Welcome to the group!"
    }
  },
  "admins": {
    "-1001234": [111, 222, 333]  // Bot-promoted admins
  },
  "settings": {
    "key": "value"
  }
}
```

## Auto Backup

- Database saved to `data/database.json`
- Auto backup to GitHub on changes
- Configurable backup interval
- Manual backup via command

## Implementation Checklist

### Phase 1: Core System
- [x] Create Database class
- [ ] Update AuthManager for 3-level permissions
- [ ] Integrate Database with existing managers
- [ ] Update command routing for new prefixes

### Phase 2: Commands
- [ ] Implement `+add` and `+del` commands
- [ ] Implement `/pm` and `/dm` commands
- [ ] Update `/lock` to use database
- [ ] Update welcome system to use database

### Phase 3: UI/UX
- [ ] Add inline buttons for `.` commands
- [ ] Add slash command suggestions for `/` commands
- [ ] Update help command with permission info

### Phase 4: Backup
- [ ] Implement GitHub auto-backup
- [ ] Add manual backup command
- [ ] Add restore functionality

## Notes

- All data changes automatically saved to database
- Database backed up to GitHub automatically
- Permission checks happen before command execution
- Inline buttons only for music controls
- Slash suggestions only for `/` commands
