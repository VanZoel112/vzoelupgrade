#!/usr/bin/env python3
"""
GitHub Sync Manager
Auto push data ke GitHub repository

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

import asyncio
import logging
import json
import aiohttp
from typing import Dict, Optional, List
from pathlib import Path
from datetime import datetime
import config

DEFAULT_AUTO_PUSH_INTERVAL = 1200

logger = logging.getLogger(__name__)

class GitHubSync:
    """Manages GitHub synchronization for data backup"""

    def __init__(self):
        self.sync_queue: List[Dict] = []
        self.is_syncing = False
        self._auto_push_task: Optional[asyncio.Task] = None
        self._repo_root = Path(config.__file__).resolve().parent

    async def push_data_to_github(self, file_path: str, content: str, commit_message: str = None) -> bool:
        """Push data to GitHub repository"""
        if not config.ENABLE_GITHUB_SYNC or not config.GITHUB_TOKEN or not config.GITHUB_REPOSITORY:
            logger.warning("GitHub configuration not available or disabled")
            return False

        try:
            if not commit_message:
                commit_message = f"Update {Path(file_path).name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

            # Prepare API request
            url = f"https://api.github.com/repos/{config.GITHUB_REPOSITORY}/contents/{file_path}"
            headers = {
                'Authorization': f'token {config.GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json',
                'Content-Type': 'application/json'
            }

            # Get current file SHA if exists
            sha = await self._get_file_sha(url, headers)

            # Prepare content (base64 encoded)
            import base64
            encoded_content = base64.b64encode(content.encode('utf-8')).decode('utf-8')

            # API payload
            payload = {
                'message': commit_message,
                'content': encoded_content,
                'branch': config.GITHUB_BRANCH
            }

            if sha:
                payload['sha'] = sha

            # Make API request
            async with aiohttp.ClientSession() as session:
                async with session.put(url, headers=headers, json=payload) as response:
                    if response.status in [200, 201]:
                        logger.info(f"Successfully pushed {file_path} to GitHub")
                        return True
                    else:
                        error_text = await response.text()
                        logger.error(f"GitHub API error: {response.status} - {error_text}")
                        return False

        except Exception as e:
            logger.error(f"Error pushing to GitHub: {e}")
            return False

    async def _get_file_sha(self, url: str, headers: Dict) -> Optional[str]:
        """Get current file SHA from GitHub"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('sha')
                    return None

        except Exception as e:
            logger.debug(f"File doesn't exist or error getting SHA: {e}")
            return None

    async def sync_lock_data(self, lock_data: Dict) -> bool:
        """Sync lock data to GitHub"""
        if not config.ENABLE_GITHUB_SYNC or not config.GITHUB_AUTO_COMMIT:
            return False

        try:
            file_path = "data/locked_users.json"
            content = json.dumps(lock_data, indent=2)
            commit_message = "🔒 Update locked users data"

            return await self.push_data_to_github(file_path, content, commit_message)

        except Exception as e:
            logger.error(f"Error syncing lock data: {e}")
            return False

    async def sync_welcome_data(self, welcome_data: Dict) -> bool:
        """Sync welcome settings to GitHub"""
        if not config.ENABLE_GITHUB_SYNC or not config.GITHUB_AUTO_COMMIT:
            return False

        try:
            file_path = "data/welcome_settings.json"
            content = json.dumps(welcome_data, indent=2)
            commit_message = "👋 Update welcome settings"

            return await self.push_data_to_github(file_path, content, commit_message)

        except Exception as e:
            logger.error(f"Error syncing welcome data: {e}")
            return False

    async def sync_config_backup(self) -> bool:
        """Sync configuration backup to GitHub"""
        if not config.ENABLE_GITHUB_SYNC or not config.GITHUB_AUTO_COMMIT:
            return False

        try:
            # Create config backup (without sensitive data)
            config_backup = {
                'features': {
                    'music': config.MUSIC_ENABLED,
                    'lock_system': config.ENABLE_LOCK_SYSTEM,
                    'premium_emoji': config.ENABLE_PREMIUM_EMOJI,
                    'tag_system': config.ENABLE_TAG_SYSTEM,
                    'welcome_system': config.ENABLE_WELCOME_SYSTEM,
                    'privacy_system': config.ENABLE_PRIVACY_SYSTEM,
                    'public_commands': config.ENABLE_PUBLIC_COMMANDS
                },
                'settings': {
                    'tag_delay': config.TAG_DELAY,
                    'music_cooldown': config.MUSIC_COOLDOWN,
                    'command_prefixes': {
                        'admin': config.PREFIX_ADMIN,
                        'dev': config.PREFIX_DEV,
                        'public': config.PREFIX_PUBLIC
                    }
                },
                'last_backup': datetime.now().isoformat()
            }

            file_path = "config/vbot_config_backup.json"
            content = json.dumps(config_backup, indent=2)
            commit_message = "⚙️ Update VBot configuration backup"

            return await self.push_data_to_github(file_path, content, commit_message)

        except Exception as e:
            logger.error(f"Error syncing config backup: {e}")
            return False

    async def queue_sync(self, sync_type: str, data: Dict):
        """Queue data for background sync"""
        sync_item = {
            'type': sync_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }

        self.sync_queue.append(sync_item)

        # Start background sync if not already running
        if not self.is_syncing:
            asyncio.create_task(self._process_sync_queue())

    def start_auto_push_loop(self) -> None:
        """Start the periodic git push loop if enabled."""

        if self._auto_push_task:
            return

        if not (config.ENABLE_GITHUB_SYNC and config.GITHUB_AUTO_PUSH):
            return

        interval = getattr(config, "GITHUB_AUTO_PUSH_INTERVAL", DEFAULT_AUTO_PUSH_INTERVAL)
        try:
            interval_value = int(interval)
        except (TypeError, ValueError):
            interval_value = DEFAULT_AUTO_PUSH_INTERVAL

        interval_value = max(60, interval_value)
        self._auto_push_task = asyncio.create_task(self._auto_push_loop(interval_value))

    async def _auto_push_loop(self, interval: int) -> None:
        """Background loop that periodically commits and pushes repo changes."""

        while True:
            await asyncio.sleep(interval)
            try:
                await self._commit_and_push_repo()
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.error(f"Auto push failed: {exc}", exc_info=True)

    async def _commit_and_push_repo(self) -> None:
        """Commit pending changes and push to the configured branch."""

        if not self._repo_root.exists():
            logger.debug("Repository root not found for auto push: %s", self._repo_root)
            return

        status_cmd = "git status --porcelain"
        status_proc = await asyncio.create_subprocess_shell(
            status_cmd,
            cwd=str(self._repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        status_stdout, status_stderr = await status_proc.communicate()

        if status_proc.returncode != 0:
            logger.warning(
                "git status failed (%s): %s",
                status_proc.returncode,
                status_stderr.decode(errors="ignore"),
            )
            return

        if not status_stdout.strip():
            logger.debug("Auto push skipped: no changes detected")
            return

        if not await self._run_git_command("git add -A"):
            return

        commit_message = datetime.now().strftime("[AutoSync] %Y-%m-%d %H:%M:%S")
        commit_cmd = f"git commit -m \"{commit_message}\""
        commit_result = await asyncio.create_subprocess_shell(
            commit_cmd,
            cwd=str(self._repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        commit_stdout, commit_stderr = await commit_result.communicate()

        if commit_result.returncode != 0:
            combined = (commit_stdout + commit_stderr).lower()
            if b"nothing to commit" in combined:
                logger.debug("Auto push: nothing to commit")
                return
            logger.warning(
                "git commit failed (%s): %s",
                commit_result.returncode,
                commit_stderr.decode(errors="ignore"),
            )
            return

        push_cmd = f"git push origin {config.GITHUB_BRANCH}"
        await self._run_git_command(push_cmd)

    async def _run_git_command(self, command: str) -> bool:
        """Execute a git command in the repository root."""

        process = await asyncio.create_subprocess_shell(
            command,
            cwd=str(self._repo_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.warning(
                "Command '%s' failed (%s): %s",
                command,
                process.returncode,
                stderr.decode(errors="ignore"),
            )
            return False

        if stdout:
            logger.debug("git output (%s): %s", command, stdout.decode(errors="ignore").strip())
        return True

    async def _process_sync_queue(self):
        """Process sync queue in background"""
        if self.is_syncing:
            return

        self.is_syncing = True

        try:
            while self.sync_queue:
                item = self.sync_queue.pop(0)
                sync_type = item['type']
                data = item['data']

                success = False
                if sync_type == 'lock_data':
                    success = await self.sync_lock_data(data)
                elif sync_type == 'welcome_data':
                    success = await self.sync_welcome_data(data)
                elif sync_type == 'config_backup':
                    success = await self.sync_config_backup()

                if success:
                    logger.debug(f"Successfully synced {sync_type}")
                else:
                    logger.warning(f"Failed to sync {sync_type}")

                # Rate limiting
                await asyncio.sleep(2)

        except Exception as e:
            logger.error(f"Error processing sync queue: {e}")

        finally:
            self.is_syncing = False

    async def create_repository_structure(self) -> bool:
        """Create initial repository structure"""
        if not config.ENABLE_GITHUB_SYNC:
            return False

        try:
            # Create README
            readme_content = """# VBot Python Data Repository

This repository contains data backups from VBot Python.

## Structure

- `data/` - Bot data backups
- `config/` - Configuration backups
- `logs/` - Log files (if enabled)

Generated by VBot Python 🎵
"""

            await self.push_data_to_github("README.md", readme_content, "📝 Initialize repository")

            # Create directory structure
            gitkeep_content = "# This file keeps the directory in git"

            await self.push_data_to_github("data/.gitkeep", gitkeep_content, "📁 Create data directory")
            await self.push_data_to_github("config/.gitkeep", gitkeep_content, "📁 Create config directory")

            logger.info("Created repository structure")
            return True

        except Exception as e:
            logger.error(f"Error creating repository structure: {e}")
            return False

    def get_sync_stats(self) -> Dict:
        """Get sync statistics"""
        return {
            'github_configured': config.ENABLE_GITHUB_SYNC,
            'auto_commit_enabled': config.GITHUB_AUTO_COMMIT,
            'queue_size': len(self.sync_queue),
            'is_syncing': self.is_syncing,
            'repository': config.GITHUB_REPOSITORY if config.ENABLE_GITHUB_SYNC else None
        }

    async def test_github_connection(self) -> bool:
        """Test GitHub API connection"""
        if not config.ENABLE_GITHUB_SYNC:
            return False

        try:
            url = f"https://api.github.com/repos/{config.GITHUB_REPOSITORY}"
            headers = {
                'Authorization': f'token {config.GITHUB_TOKEN}',
                'Accept': 'application/vnd.github.v3+json'
            }

            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers) as response:
                    if response.status == 200:
                        logger.info("GitHub connection test successful")
                        return True
                    else:
                        logger.error(f"GitHub connection test failed: {response.status}")
                        return False

        except Exception as e:
            logger.error(f"GitHub connection test error: {e}")
            return False