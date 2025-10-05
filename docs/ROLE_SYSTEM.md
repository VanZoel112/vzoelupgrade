# Auto Role Detection System

## Overview

VBot sekarang memiliki sistem **auto-detect role** yang mendeteksi status user secara otomatis dan memberikan hak akses yang sesuai. Sistem menggunakan caching untuk performa optimal.

---

## Role Hierarchy

```
Developer (👨‍💻)
    ↓
Owner (👑)
    ↓
Admin (⚡)
    ↓
User (👤)
```

### Role Levels

#### 1. **Developer** (Highest)
- Configured in `config.DEVELOPER_IDS`
- **Full access** to all commands
- **Bypass** all permission checks
- Auto-granted admin rights in all groups
- Can manage bot configuration

**Permissions:**
- ✅ Owner commands (`+` prefix)
- ✅ Admin commands (`/` prefix)
- ✅ Public commands (`.` prefix)
- ✅ Bypass all checks

#### 2. **Owner**
- Configured in `config.OWNER_ID`
- Full bot privileges
- Same access as developer
- Auto-granted admin rights in all groups

**Permissions:**
- ✅ Owner commands (`+` prefix)
- ✅ Admin commands (`/` prefix)
- ✅ Public commands (`.` prefix)
- ✅ Bypass all checks

#### 3. **Admin**
- **Auto-detected** from Telegram group admin status
- Elevated privileges in their groups
- Access to admin commands
- **Cached for 3 minutes** for performance

**Permissions:**
- ❌ Owner commands
- ✅ Admin commands (`/` prefix)
- ✅ Public commands (`.` prefix)
- ❌ Bypass checks

#### 4. **User** (Default)
- Regular group members
- Basic access only
- Public commands available

**Permissions:**
- ❌ Owner commands
- ❌ Admin commands
- ✅ Public commands (`.` prefix)
- ❌ Bypass checks

---

## Auto-Detection Process

```python
async def get_user_role(client, user_id, chat_id):
    # Check cache first (5-minute TTL)
    if cached:
        return cached_role

    # Detect role hierarchy
    if is_developer(user_id):
        return "developer"
    elif is_owner(user_id):
        return "owner"
    elif is_admin_in_chat(client, user_id, chat_id):
        return "admin"  # Auto-detected from Telegram!
    else:
        return "user"
```

### Caching System

**Role Cache:**
- TTL: **5 minutes**
- Key: `(user_id, chat_id)`
- Auto-cleans old entries (keeps last 1000)

**Admin Cache:**
- TTL: **3 minutes**
- Key: `(user_id, chat_id)`
- Faster refresh for admin status changes

**Benefits:**
- ⚡ Reduced API calls to Telegram
- 🚀 Faster permission checks
- 📊 Better performance in large groups
- 🔄 Auto-refresh every 3-5 minutes

---

## Commands

### Role Information

#### `/role` or `.role` or `+role`
Display current user's role and permissions.

**Output:**
```
Role Information

⚡ Role: ADMIN
👤 User: @username
🆔 User ID: 123456789
💬 Chat ID: -1001234567890

Permissions:
├ Owner Commands: ❌
├ Admin Commands: ✅
├ Public Commands: ✅
└ Bypass All Checks: ❌

Description:
Group admin with elevated privileges

Available Commands:
[List of available commands based on role]
```

#### `/refreshrole`
Manually refresh role cache for current user.

**Use cases:**
- Just became admin in group
- Need immediate permission update
- Troubleshooting permission issues

**Output:**
```
✅ Cache cleared for user 123456789 in chat -1001234567890
🔄 New role detected: ADMIN

Your permissions have been updated based on current admin status.
```

#### `/listdevs` or `.listdevs`
Show list of developers and owner.

**Output:**
```
Bot Administrators

👑 Owner:
@owner_username (8024282347)

👨‍💻 Developers: (2 total)
• @dev1 (8024282347)
• @dev2 (7553981355)

Privileges:
• Full access to all commands
• Bypass all permission checks
• Can manage bot configuration
• Auto-granted admin rights in all groups
```

#### `/clearcache [all|chat|user]` (Developer Only)
Clear role cache manually.

**Options:**
- `all` - Clear all cache (all users, all chats)
- `chat` - Clear cache for current chat
- `user` - Clear cache for current user

**Examples:**
```bash
/clearcache          # Clear current chat
/clearcache all      # Clear everything
/clearcache user     # Clear current user
```

---

## Permission Flow

### Old Flow (Before)
```
Message → Check Command Type → Check Permissions → Error or Execute
```
**Problem:** Could fail in private chats, no caching

### New Flow (After)
```
Message
  ↓
Check if Registered Command
  ↓
Check if Private Chat → Skip Permission (Userbot Mode)
  ↓
Get User Role (Cached) ← Auto-detect admin status!
  ↓
Check Role Permissions
  ↓
Execute or Deny
```

**Improvements:**
- ✅ Auto-detect admin status
- ✅ Cache role for performance
- ✅ Private chat bypass
- ✅ Clear role hierarchy
- ✅ Developer/Owner auto-bypass

---

## Configuration

### config.py

```python
# Owner (single user)
OWNER_ID = 8024282347

# Developers (multiple users)
DEVELOPER_IDS = [
    8024282347,  # Main Developer
    7553981355   # Secondary Developer
]

# Admin Chat IDs (auto-grant admin to all members)
ADMIN_CHAT_IDS = []  # Optional

# Enable public commands
ENABLE_PUBLIC_COMMANDS = True
```

---

## Auto-Grant Admin Rights

### How It Works

When a user is detected as:
1. **Developer** → Auto-granted admin rights everywhere
2. **Owner** → Auto-granted admin rights everywhere
3. **Group Admin** → Auto-detected from Telegram API

```python
async def is_admin_in_chat(client, user_id, chat_id):
    # Developer/Owner bypass
    if is_developer(user_id) or is_owner(user_id):
        return True  # ✅ Auto-granted!

    # Check cache
    if cached:
        return cached_admin_status

    # Fetch from Telegram
    perms = await client.get_permissions(chat_id, user_id)
    is_admin = perms.is_admin or perms.is_creator

    # Cache result (3 minutes)
    cache_admin_status(user_id, chat_id, is_admin)

    return is_admin
```

### Benefits

- 👨‍💻 Developers can manage any group
- 👑 Owner has full control
- ⚡ Group admins auto-detected
- 🚀 No manual permission setup needed
- 📊 Permissions sync with Telegram automatically

---

## Troubleshooting

### Permission Denied Error

**Problem:**
```
Akses ditolak. Hanya admin grup yang dapat memakai perintah ini.
```

**Solutions:**

1. **Check Your Role:**
   ```
   /role
   ```
   See your current role and permissions

2. **Refresh Role Cache:**
   ```
   /refreshrole
   ```
   Force immediate role re-detection

3. **Verify Admin Status:**
   - Are you admin in this group on Telegram?
   - Check with: `/adminlist`

4. **Clear Cache (Developer):**
   ```
   /clearcache all
   ```

### Role Not Updating

**Scenario:** Just became admin, but bot still sees you as user

**Solution:**
```
/refreshrole
```

Or wait 3-5 minutes for auto-refresh.

### Private Chat Issues

**Good News:** Private chats now **bypass** permission checks!

All registered commands work in private chat (userbot mode).

---

## Use Cases

### Scenario 1: New Group Admin
```
User becomes admin in Telegram
   ↓
First command triggers auto-detect
   ↓
Bot checks Telegram API
   ↓
Detects admin status
   ↓
Caches role as "admin" (3 min)
   ↓
✅ Admin commands now accessible
```

### Scenario 2: Developer Joins Group
```
Developer joins new group
   ↓
Sends any command
   ↓
Bot checks developer_ids
   ↓
Matches user_id
   ↓
Auto-grants admin rights
   ↓
✅ Full access immediately (no setup needed!)
```

### Scenario 3: Permission Troubleshooting
```
User reports "access denied"
   ↓
User runs /role
   ↓
Bot shows: "Role: USER"
   ↓
User checks Telegram admin list
   ↓
Realizes they're not admin
   ↓
✅ Issue identified
```

---

## Technical Details

### Cache Management

**Auto-Cleanup:**
- Runs when cache exceeds 1000 entries
- Removes expired entries (older than TTL)
- Keeps system memory efficient

**Manual Cleanup:**
```python
# Clear specific user in specific chat
auth_manager.clear_role_cache(user_id=123, chat_id=456)

# Clear all for user
auth_manager.clear_role_cache(user_id=123)

# Clear all for chat
auth_manager.clear_role_cache(chat_id=456)

# Clear everything
auth_manager.clear_role_cache()
```

### Permission Checks

```python
# Get role
role = await auth_manager.get_user_role(client, user_id, chat_id)

# Get permissions
perms = auth_manager.get_role_permissions(role)

# Check specific permission
if perms['admin_commands']:
    # User can use admin commands
```

---

## API Reference

### AuthManager Methods

#### `async get_user_role(client, user_id, chat_id) -> str`
Auto-detect user role with caching.

**Returns:** `"developer"` | `"owner"` | `"admin"` | `"user"`

#### `async is_admin_in_chat(client, user_id, chat_id) -> bool`
Check if user is admin (cached, auto-grants dev/owner).

#### `clear_role_cache(user_id=None, chat_id=None)`
Clear role cache manually.

#### `get_role_permissions(role: str) -> dict`
Get permission dictionary for role.

---

**2025© VBot - Vzoel Fox's**
