#!/usr/bin/env python3
"""
Database Manager - JSON-based database with GitHub backup
Stores all bot data including permissions, settings, locks, etc.

Author: VanZoel112
Version: 2.0.0
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
import asyncio
import subprocess
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    """JSON database manager with auto-backup"""

    def __init__(self, db_path: str = "data/database.json", enable_auto_backup: bool = True):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(exist_ok=True)
        self.data = self._load()
        self._ensure_structure()

        # Auto-backup settings
        self.enable_auto_backup = enable_auto_backup
        self.backup_task = None
        self.backup_pending = False
        self.last_backup = None

    def _load(self) -> Dict:
        """Load database from file"""
        if self.db_path.exists():
            try:
                with open(self.db_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading database: {e}")
                return {}
        return {}

    def _save(self):
        """Save database to file"""
        try:
            with open(self.db_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            logger.debug("Database saved successfully")

            # Schedule auto-backup if enabled
            if self.enable_auto_backup and not self.backup_pending:
                self.backup_pending = True
                # Use asyncio to schedule backup after 5 seconds (debounce)
                try:
                    asyncio.create_task(self._delayed_backup())
                except RuntimeError:
                    # If no event loop is running, skip async backup
                    pass

        except Exception as e:
            logger.error(f"Error saving database: {e}")

    def _ensure_structure(self):
        """Ensure database has required structure"""
        if 'permissions' not in self.data:
            self.data['permissions'] = {}  # user_id: permission_level

        if 'locks' not in self.data:
            self.data['locks'] = {}  # chat_id: {user_id: True}

        if 'welcome' not in self.data:
            self.data['welcome'] = {}  # chat_id: {enabled: bool, message: str}

        if 'admins' not in self.data:
            self.data['admins'] = {}  # chat_id: [user_ids]

        if 'settings' not in self.data:
            self.data['settings'] = {}

        self._save()

    # ==============================================
    # PERMISSION MANAGEMENT
    # ==============================================

    def add_permission(self, user_id: int, chat_id: int = None):
        """Give user permission to use / commands (non-admin)"""
        key = f"{chat_id}:{user_id}" if chat_id else str(user_id)
        if 'authorized_users' not in self.data:
            self.data['authorized_users'] = []
        if key not in self.data['authorized_users']:
            self.data['authorized_users'].append(key)
            self._save()
            return True
        return False

    def remove_permission(self, user_id: int, chat_id: int = None):
        """Remove user permission"""
        key = f"{chat_id}:{user_id}" if chat_id else str(user_id)
        if 'authorized_users' not in self.data:
            self.data['authorized_users'] = []
        if key in self.data['authorized_users']:
            self.data['authorized_users'].remove(key)
            self._save()
            return True
        return False

    def has_permission(self, user_id: int, chat_id: int = None) -> bool:
        """Check if user has / command permission"""
        key = f"{chat_id}:{user_id}" if chat_id else str(user_id)
        global_key = str(user_id)
        if 'authorized_users' not in self.data:
            return False
        return key in self.data['authorized_users'] or global_key in self.data['authorized_users']

    def get_authorized_users(self, chat_id: int = None) -> List[int]:
        """Get list of authorized users for a chat"""
        if 'authorized_users' not in self.data:
            return []

        if chat_id:
            prefix = f"{chat_id}:"
            users = []
            for key in self.data['authorized_users']:
                if key.startswith(prefix):
                    users.append(int(key.split(':')[1]))
                elif ':' not in key:  # Global permission
                    users.append(int(key))
            return users
        else:
            return [int(k.split(':')[-1]) for k in self.data['authorized_users']]

    # ==============================================
    # LOCK SYSTEM
    # ==============================================

    def lock_user(self, chat_id: int, user_id: int):
        """Lock user in chat (auto-delete their messages)"""
        chat_key = str(chat_id)
        if chat_key not in self.data['locks']:
            self.data['locks'][chat_key] = []
        if user_id not in self.data['locks'][chat_key]:
            self.data['locks'][chat_key].append(user_id)
            self._save()

    def unlock_user(self, chat_id: int, user_id: int):
        """Unlock user in chat"""
        chat_key = str(chat_id)
        if chat_key in self.data['locks'] and user_id in self.data['locks'][chat_key]:
            self.data['locks'][chat_key].remove(user_id)
            self._save()

    def is_locked(self, chat_id: int, user_id: int) -> bool:
        """Check if user is locked"""
        chat_key = str(chat_id)
        return chat_key in self.data['locks'] and user_id in self.data['locks'][chat_key]

    def get_locked_users(self, chat_id: int) -> List[int]:
        """Get locked users in chat"""
        chat_key = str(chat_id)
        return self.data['locks'].get(chat_key, [])

    # ==============================================
    # WELCOME SYSTEM
    # ==============================================

    def set_welcome(self, chat_id: int, message: str, enabled: bool = True):
        """Set welcome message for chat"""
        chat_key = str(chat_id)
        self.data['welcome'][chat_key] = {
            'enabled': enabled,
            'message': message
        }
        self._save()

    def get_welcome(self, chat_id: int) -> Optional[Dict]:
        """Get welcome settings"""
        chat_key = str(chat_id)
        return self.data['welcome'].get(chat_key)

    def toggle_welcome(self, chat_id: int, enabled: bool):
        """Enable/disable welcome"""
        chat_key = str(chat_id)
        if chat_key in self.data['welcome']:
            self.data['welcome'][chat_key]['enabled'] = enabled
            self._save()

    # ==============================================
    # ADMIN SYSTEM
    # ==============================================

    def add_admin(self, chat_id: int, user_id: int):
        """Add admin to chat"""
        chat_key = str(chat_id)
        if chat_key not in self.data['admins']:
            self.data['admins'][chat_key] = []
        if user_id not in self.data['admins'][chat_key]:
            self.data['admins'][chat_key].append(user_id)
            self._save()

    def remove_admin(self, chat_id: int, user_id: int):
        """Remove admin from chat"""
        chat_key = str(chat_id)
        if chat_key in self.data['admins'] and user_id in self.data['admins'][chat_key]:
            self.data['admins'][chat_key].remove(user_id)
            self._save()

    def get_admins(self, chat_id: int) -> List[int]:
        """Get admin list"""
        chat_key = str(chat_id)
        return self.data['admins'].get(chat_key, [])

    # ==============================================
    # SETTINGS
    # ==============================================

    def set_setting(self, key: str, value: Any):
        """Set a setting"""
        self.data['settings'][key] = value
        self._save()

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Get a setting"""
        return self.data['settings'].get(key, default)

    # ==============================================
    # UTILITY
    # ==============================================

    def get_stats(self) -> Dict:
        """Get database statistics"""
        return {
            'authorized_users': len(self.data.get('authorized_users', [])),
            'locked_users': sum(len(v) for v in self.data['locks'].values()),
            'welcome_chats': len(self.data['welcome']),
            'admin_chats': len(self.data['admins']),
            'database_size': self.db_path.stat().st_size if self.db_path.exists() else 0
        }

    def export_data(self) -> str:
        """Export database as JSON string"""
        return json.dumps(self.data, indent=2, ensure_ascii=False)

    def import_data(self, data: str):
        """Import database from JSON string"""
        self.data = json.loads(data)
        self._save()

    # ==============================================
    # GITHUB AUTO-BACKUP
    # ==============================================

    async def _delayed_backup(self):
        """Delayed backup with debounce (5 seconds)"""
        await asyncio.sleep(5)
        await self.backup_to_github()
        self.backup_pending = False

    async def backup_to_github(self) -> bool:
        """Backup database to GitHub"""
        try:
            # Check if git is configured
            result = subprocess.run(
                ['git', 'rev-parse', '--git-dir'],
                capture_output=True,
                text=True,
                cwd=str(self.db_path.parent.parent)
            )

            if result.returncode != 0:
                logger.warning("Not a git repository - skipping auto-backup")
                return False

            # Add database file
            subprocess.run(
                ['git', 'add', str(self.db_path.relative_to(self.db_path.parent.parent))],
                cwd=str(self.db_path.parent.parent),
                check=False
            )

            # Check if there are changes
            result = subprocess.run(
                ['git', 'diff', '--cached', '--quiet'],
                cwd=str(self.db_path.parent.parent)
            )

            if result.returncode == 0:
                # No changes
                logger.debug("No database changes to backup")
                return True

            # Commit changes
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            commit_msg = f"Auto-backup database - {timestamp}"

            subprocess.run(
                ['git', 'commit', '-m', commit_msg],
                cwd=str(self.db_path.parent.parent),
                capture_output=True,
                check=False
            )

            # Push to remote (non-blocking)
            subprocess.Popen(
                ['git', 'push', 'origin', 'main'],
                cwd=str(self.db_path.parent.parent),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            self.last_backup = datetime.now()
            logger.info(f"✅ Database backed up to GitHub")
            return True

        except Exception as e:
            logger.error(f"Failed to backup to GitHub: {e}")
            return False

    async def manual_backup(self, commit_message: str = None) -> bool:
        """Manual backup to GitHub with custom commit message"""
        try:
            # Add database file
            subprocess.run(
                ['git', 'add', str(self.db_path.relative_to(self.db_path.parent.parent))],
                cwd=str(self.db_path.parent.parent),
                check=True
            )

            # Commit with custom message
            if not commit_message:
                commit_message = f"Manual database backup - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            subprocess.run(
                ['git', 'commit', '-m', commit_message],
                cwd=str(self.db_path.parent.parent),
                capture_output=True,
                check=False
            )

            # Push to remote
            result = subprocess.run(
                ['git', 'push', 'origin', 'main'],
                cwd=str(self.db_path.parent.parent),
                capture_output=True,
                text=True
            )

            if result.returncode == 0:
                logger.info("✅ Manual backup successful")
                return True
            else:
                logger.error(f"Failed to push: {result.stderr}")
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Manual backup failed: {e}")
            return False

    def get_backup_stats(self) -> Dict:
        """Get backup statistics"""
        return {
            'auto_backup_enabled': self.enable_auto_backup,
            'last_backup': self.last_backup.isoformat() if self.last_backup else None,
            'backup_pending': self.backup_pending
        }
