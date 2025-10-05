# Auto Lock-Back System

## Overview

VBot memiliki sistem **auto lock-back** yang otomatis me-lock balik user yang mencoba lock role yang lebih tinggi. Sistem ini melindungi Founder dan Orang Dalam dari abuse lock command.

---

## Lock-Back Rules

### Hierarchy Protection

```
🔱 Founder (Developer)
    ↓ IMMUNE - Tidak bisa di-lock siapapun
🎖️ Orang Dalam (Owner)
    ↓ Hanya bisa di-lock oleh Founder
👤 Admin/User
    ↓ Bisa di-lock oleh Founder atau Orang Dalam
```

### Rule 1: Founder Lock Anyone → NO Lockback

**Scenario:**
```
Founder uses: /lock @anyuser
Result: ✅ User locked, NO lockback
```

**Explanation:**
- Founder (Developer ID) **IMMUNE** dari semua lock
- Bisa lock siapapun tanpa konsekuensi
- Tidak ada yang bisa lock-back Founder

---

### Rule 2: Orang Dalam Lock Founder → Orang Dalam Locked Back

**Scenario:**
```
Orang Dalam uses: /lock @founder
Result: ❌ Orang Dalam locked back automatically
```

**Message:**
```
⚠️ Auto Lock-Back Activated

@orangdalam mencoba lock Founder dan di-lock balik otomatis.

Alasan: Mencoba lock Founder (Developer).
Hanya Founder yang dapat unlock pembatasan ini.
```

**Explanation:**
- Orang Dalam tidak bisa lock Founder
- Auto locked back sebagai punishment
- Hanya Founder yang bisa unlock

---

### Rule 3: Admin/User Lock Founder → Locked Back

**Scenario:**
```
Admin uses: /lock @founder
Result: ❌ Admin locked back automatically
```

**Message:**
```
⚠️ Auto Lock-Back Activated

@adminuser mencoba lock Founder dan di-lock balik otomatis.

Alasan: Mencoba lock Founder (Developer).
Hanya Founder yang dapat unlock pembatasan ini.
```

**Explanation:**
- Non-Founder tidak bisa lock Founder
- Auto locked back sebagai punishment
- Pesan dikirim ke group sebagai peringatan

---

### Rule 4: Admin/User Lock Orang Dalam → Locked Back

**Scenario:**
```
Admin uses: /lock @orangdalam
Result: ❌ Admin locked back automatically
```

**Message:**
```
⚠️ Auto Lock-Back Activated

@adminuser mencoba lock Orang Dalam dan di-lock balik otomatis.

Alasan: Mencoba lock Orang Dalam (Owner).
Hanya Founder atau Orang Dalam yang dapat unlock pembatasan ini.
```

**Explanation:**
- Admin tidak bisa lock Orang Dalam
- Auto locked back sebagai punishment
- Hanya Founder atau Orang Dalam yang bisa unlock

---

## How It Works

### Lock Command Flow

```
User: /lock @target
    ↓
Bot checks issuer role (Founder/Orang Dalam/User)
    ↓
Bot checks target role
    ↓
Is target higher role than issuer?
    ↓ YES
Apply LOCKBACK to issuer
Show lockback message
    ↓ NO
Lock target normally
```

### Lockback Metadata

When lockback applied, system stores:
```json
{
  "requires_developer": true,
  "reason": "Mencoba lock Founder (Developer)...",
  "locked_for": "protected_account_attempt",
  "protected_role": "Founder",
  "protected_user_id": 123456789
}
```

**Features:**
- `requires_developer`: Only Founder can unlock
- Stores reason for lockback
- Records protected role that was targeted
- Logs protected user ID

---

## Permission Matrix

| Issuer Role | Target: Founder | Target: Orang Dalam | Target: Admin/User |
|-------------|-----------------|---------------------|-------------------|
| **Founder** 🔱 | ✅ Lock (no lockback) | ✅ Lock | ✅ Lock |
| **Orang Dalam** 🎖️ | ❌ **LOCKBACK** | ✅ Lock | ✅ Lock |
| **Admin/User** 👤 | ❌ **LOCKBACK** | ❌ **LOCKBACK** | ✅ Lock |

---

## Unlock Restrictions

### Who Can Unlock Lockbacks?

**Lockback for trying to lock Founder:**
- ✅ **Founder only** dapat unlock
- ❌ Orang Dalam tidak bisa unlock
- ❌ Admin tidak bisa unlock

**Lockback for trying to lock Orang Dalam:**
- ✅ **Founder** dapat unlock
- ✅ **Orang Dalam** dapat unlock
- ❌ Admin tidak bisa unlock

### Unlock Command
```
/unlock @locked_user
```

**Requirements:**
- Must have permission based on lockback type
- Founder can unlock anyone
- Orang Dalam can unlock non-Founder lockbacks

---

## Examples

### Example 1: Admin Tries to Lock Founder

**Setup:**
- Admin: @adminuser (ID: 111111)
- Founder: @founder (ID: 8024282347)

**Command:**
```
Admin: /lock @founder
```

**Result:**
```
⚠️ Auto Lock-Back Activated

@adminuser mencoba lock Founder dan di-lock balik otomatis.

Alasan: Mencoba lock Founder (Developer).
Hanya Founder yang dapat unlock pembatasan ini.
```

**Effect:**
- ❌ @founder NOT locked
- ✅ @adminuser LOCKED automatically
- 🔒 @adminuser's messages auto-deleted
- 👨‍💻 Only Founder can unlock @adminuser

---

### Example 2: Orang Dalam Tries to Lock Founder

**Setup:**
- Orang Dalam: @owner (ID: 7553981355)
- Founder: @founder (ID: 8024282347)

**Command:**
```
Orang Dalam: /lock @founder
```

**Result:**
```
⚠️ Auto Lock-Back Activated

@owner mencoba lock Founder dan di-lock balik otomatis.

Alasan: Mencoba lock Founder (Developer).
Hanya Founder yang dapat unlock pembatasan ini.
```

**Effect:**
- ❌ @founder NOT locked
- ✅ @owner LOCKED automatically
- 🔒 @owner's messages auto-deleted until unlock

---

### Example 3: Admin Tries to Lock Orang Dalam

**Setup:**
- Admin: @adminuser (ID: 222222)
- Orang Dalam: @owner (ID: 7553981355)

**Command:**
```
Admin: /lock @owner
```

**Result:**
```
⚠️ Auto Lock-Back Activated

@adminuser mencoba lock Orang Dalam dan di-lock balik otomatis.

Alasan: Mencoba lock Orang Dalam (Owner).
Hanya Founder atau Orang Dalam yang dapat unlock pembatasan ini.
```

**Effect:**
- ❌ @owner NOT locked
- ✅ @adminuser LOCKED automatically
- 👑 Founder or Orang Dalam can unlock @adminuser

---

### Example 4: Founder Locks Anyone (No Lockback)

**Setup:**
- Founder: @founder (ID: 8024282347)
- Target: @anyuser

**Command:**
```
Founder: /lock @anyuser
```

**Result:**
```
🔒 User Locked

@anyuser has been locked.
Reason: Locked by admin
```

**Effect:**
- ✅ @anyuser LOCKED
- ❌ NO lockback (Founder immune)
- 🔓 Founder can lock anyone freely

---

## Benefits

### Security
- ✅ Protects Founder from all lock attempts
- ✅ Protects Orang Dalam from non-authorized locks
- ✅ Auto-punishment prevents abuse
- ✅ Hierarchy maintained automatically

### Transparency
- ✅ Clear lockback messages
- ✅ Role names displayed (Founder/Orang Dalam)
- ✅ Reason shown to everyone
- ✅ Unlock requirements stated

### Logging
- ✅ All lockback attempts logged
- ✅ Warning level in logs
- ✅ Metadata stored for audit
- ✅ Can track abuse patterns

---

## Technical Details

### Code Location
`main.py` → `_handle_lock_command()` (line ~3273)

### Logic Flow
```python
# Check roles
is_target_developer = auth_manager.is_developer(target_user_id)
is_target_owner = auth_manager.is_owner(target_user_id)
is_issuer_developer = auth_manager.is_developer(issuer_id)
is_issuer_owner = auth_manager.is_owner(issuer_id)

# Rule 1: Developer immune
if is_issuer_developer:
    pass  # No lockback

# Rule 2: Owner lock Developer → lockback
elif is_issuer_owner and is_target_developer:
    lockback(issuer_id, "Founder")

# Rule 3: Non-developer lock Developer → lockback
elif not is_issuer_developer and is_target_developer:
    lockback(issuer_id, "Founder")

# Rule 4: Non-owner/developer lock Owner → lockback
elif not is_issuer_developer and not is_issuer_owner and is_target_owner:
    lockback(issuer_id, "Orang Dalam")
```

### Lockback Function
```python
async def lockback(issuer_id, protected_role):
    metadata = {
        'requires_developer': True,
        'reason': f"Mencoba lock {protected_role}...",
        'locked_for': 'protected_account_attempt',
        'protected_role': protected_role,
        'protected_user_id': target_user_id,
    }

    await lock_manager.lock_user(
        chat_id, issuer_id, reason, metadata
    )
```

---

## FAQ

### Q: Bagaimana cara unlock dari lockback?

**A:** Hanya role yang berwenang bisa unlock:
- Lockback from Founder attempt: Hanya Founder
- Lockback from Orang Dalam attempt: Founder atau Orang Dalam

Command: `/unlock @locked_user`

### Q: Apakah Founder bisa di-lock?

**A:** **TIDAK**. Founder (Developer ID) sepenuhnya IMMUNE dari lock.

### Q: Apakah lockback permanen?

**A:** Tidak, tapi hanya Founder (atau Orang Dalam untuk kasus tertentu) yang bisa unlock.

### Q: Apakah bisa disable lockback?

**A:** Tidak, ini fitur security untuk melindungi hierarchy.

### Q: Apa yang terjadi saat locked back?

**A:**
1. User otomatis di-lock
2. Semua message user auto-delete
3. Message lockback dikirim ke group
4. Metadata tersimpan di database
5. Hanya role authorized yang bisa unlock

---

**2025© VBot - Vzoel Fox's**
