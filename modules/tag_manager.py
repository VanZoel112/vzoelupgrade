#!/usr/bin/env python3
"""
Tag System Manager
Progressive tag all members dengan message editing

Author: Vzoel Fox's
Version: 2.0.0 Python
"""

import asyncio
import logging
from typing import Dict, List, Set, Optional
from telethon.tl.types import Channel, Chat
import config

logger = logging.getLogger(__name__)

class TagManager:
    """Manages progressive tagging of all members"""

    def __init__(self):
        
        self.active_tags: Dict[int, Dict] = {}  # chat_id -> tag session info
        self.cancelled_tags: Set[int] = set()  # chat_ids with cancelled tags

    async def start_tag_all(
        self,
        client,
        chat_id: int,
        message: str,
        sender_id: int,
        *,
        batch_size: Optional[int] = None,
        reply_to_msg_id: Optional[int] = None,
    ) -> bool:
        """Start progressive tag all process"""
        try:
            # Check if already tagging in this chat
            if chat_id in self.active_tags:
                return False

            # Get all members
            members = await self._get_chat_members(client, chat_id)
            if not members:
                return False

            # Determine batch size (ensure sane limits)
            configured_batch = config.TAG_BATCH_SIZE if config.TAG_BATCH_SIZE > 0 else 5
            resolved_batch = batch_size if batch_size and batch_size > 0 else configured_batch
            resolved_batch = max(1, min(resolved_batch, 25))

            # Initialize tag session
            self.active_tags[chat_id] = {
                'members': members,
                'message': message,
                'sender_id': sender_id,
                'current_index': 0,
                'message_obj': None,
                'tagged_count': 0,
                'batch_size': resolved_batch,
                'reply_to': reply_to_msg_id,
            }

            # Remove from cancelled set if present
            self.cancelled_tags.discard(chat_id)

            # Start tagging process
            asyncio.create_task(self._progressive_tag_process(client, chat_id))

            logger.info(
                "Started tag all for %s members in chat %s (batch_size=%s)",
                len(members),
                chat_id,
                resolved_batch,
            )
            return True

        except Exception as e:
            logger.error(f"Error starting tag all: {e}")
            return False

    async def cancel_tag_all(self, chat_id: int) -> bool:
        """Cancel ongoing tag all process"""
        try:
            if chat_id in self.active_tags:
                self.cancelled_tags.add(chat_id)
                logger.info(f"Cancelled tag all in chat {chat_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error cancelling tag all: {e}")
            return False

    async def _get_chat_members(self, client, chat_id: int) -> List[int]:
        """Get all member IDs from chat"""
        try:
            members = []
            async for user in client.iter_participants(chat_id):
                if not user.bot and not user.deleted:
                    members.append(user.id)

            return members

        except Exception as e:
            logger.error(f"Error getting chat members: {e}")
            return []

    async def _progressive_tag_process(self, client, chat_id: int):
        """Progressive tagging process with message editing"""
        try:
            session = self.active_tags[chat_id]
            members = session['members']
            base_message = session['message']
            batch_size = session.get('batch_size', 5)

            # Send initial message
            initial_text = f"{base_message}\n\n⏳ Starting tag process..."
            message_obj = await client.send_message(
                chat_id,
                initial_text,
                reply_to=session.get('reply_to'),
            )
            session['message_obj'] = message_obj

            # Progressive tagging
            while session['current_index'] < len(members):
                # Check if cancelled
                if chat_id in self.cancelled_tags:
                    await self._handle_tag_cancellation(client, chat_id)
                    return

                # Get batch of users to tag
                start_idx = session['current_index']
                end_idx = min(start_idx + batch_size, len(members))
                batch_members = members[start_idx:end_idx]

                # Create mention text
                mentions = []
                for user_id in batch_members:
                    try:
                        user = await client.get_entity(user_id)
                        if hasattr(user, 'username') and user.username:
                            mentions.append(f"@{user.username}")
                        else:
                            mentions.append(f"[User](tg://user?id={user_id})")
                    except:
                        mentions.append(f"[User](tg://user?id={user_id})")

                # Update message with current batch
                progress = f"({session['tagged_count'] + len(batch_members)}/{len(members)})"
                updated_text = f"{base_message}\n\n{' '.join(mentions)}\n\n📊 Progress: {progress}"

                try:
                    await message_obj.edit(updated_text)
                except Exception as edit_error:
                    logger.warning(f"Failed to edit message: {edit_error}")

                # Update session
                session['current_index'] = end_idx
                session['tagged_count'] += len(batch_members)

                # Delay between edits
                await asyncio.sleep(config.TAG_DELAY)

            # Final message
            final_text = f"{base_message}\n\n✅ Tagged all {len(members)} members!"
            try:
                await message_obj.edit(final_text)
            except:
                pass

            # Cleanup
            self._cleanup_tag_session(chat_id)

        except Exception as e:
            logger.error(f"Error in progressive tag process: {e}")
            self._cleanup_tag_session(chat_id)

    async def _handle_tag_cancellation(self, client, chat_id: int):
        """Handle tag cancellation"""
        try:
            session = self.active_tags.get(chat_id)
            if session and session.get('message_obj'):
                try:
                    cancel_text = f"{session['message']}\n\n❌ Tag process cancelled by admin."
                    await session['message_obj'].edit(cancel_text)
                except:
                    pass

            self._cleanup_tag_session(chat_id)

        except Exception as e:
            logger.error(f"Error handling tag cancellation: {e}")

    def _cleanup_tag_session(self, chat_id: int):
        """Clean up tag session"""
        self.active_tags.pop(chat_id, None)
        self.cancelled_tags.discard(chat_id)
