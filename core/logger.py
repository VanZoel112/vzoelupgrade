#!/usr/bin/env python3
"""
VBot Advanced Logging System
Auto-send logs to Telegram group with SQL integration

Author: VanZoel112
Version: 2.0.0
"""

import asyncio
import logging
import sys
import traceback
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Optional, Dict, Any
import aiosqlite

# Telegram log group ID
LOG_GROUP_ID = -4775943821

class TelegramLogHandler(logging.Handler):
    """Send logs to Telegram group in real-time"""

    def __init__(self, client, log_group_id: int = LOG_GROUP_ID, level=logging.WARNING):
        super().__init__(level)
        self.client = client
        self.log_group_id = log_group_id
        self._running = False

    def emit(self, record):
        """Send log record to Telegram"""
        try:
            if not self._running or not self.client:
                return

            log_entry = self.format(record)

            # Add to async queue
            asyncio.create_task(self._send_to_telegram(log_entry, record))

        except Exception:
            self.handleError(record)

    async def _send_to_telegram(self, message: str, record):
        """Async send to Telegram group"""
        try:
            if not self.client:
                return

            # Emoji mapping
            emoji_map = {
                'DEBUG': '🔍',
                'INFO': 'ℹ️',
                'WARNING': '⚠️',
                'ERROR': '❌',
                'CRITICAL': '🚨'
            }

            emoji = emoji_map.get(record.levelname, '📋')
            timestamp = datetime.now().strftime('%H:%M:%S')

            formatted_msg = (
                f"{emoji} **{record.levelname}** | `{timestamp}`\n\n"
                f"```\n{message}\n```"
            )

            # Limit message length
            if len(formatted_msg) > 4000:
                formatted_msg = formatted_msg[:3900] + "\n...\n```\n*[Truncated]*"

            # Send to log group
            await self.client.send_message(
                self.log_group_id,
                formatted_msg
            )

        except Exception as e:
            print(f"Failed to send log to Telegram: {e}")

    def start(self):
        """Start the handler"""
        self._running = True

    def stop(self):
        """Stop the handler"""
        self._running = False


class SQLiteLogHandler(logging.Handler):
    """Store logs in SQLite database"""

    def __init__(self, db_path: str = "data/logs.db", level=logging.INFO):
        super().__init__(level)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        asyncio.create_task(self._init_db())

    async def _init_db(self):
        """Initialize database table"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        level TEXT NOT NULL,
                        logger_name TEXT,
                        message TEXT NOT NULL,
                        module TEXT,
                        function TEXT,
                        line_number INTEGER,
                        exception TEXT
                    )
                """)

                # Create indexes
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_timestamp
                    ON logs(timestamp DESC)
                """)

                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_level
                    ON logs(level)
                """)

                await db.commit()
        except Exception as e:
            print(f"Failed to init log database: {e}")

    def emit(self, record):
        """Save log record to database"""
        try:
            log_data = {
                'timestamp': datetime.fromtimestamp(record.created),
                'level': record.levelname,
                'logger_name': record.name,
                'message': record.getMessage(),
                'module': record.module,
                'function': record.funcName,
                'line_number': record.lineno,
                'exception': self._format_exception(record) if record.exc_info else None
            }

            asyncio.create_task(self._save_to_db(log_data))

        except Exception:
            self.handleError(record)

    def _format_exception(self, record):
        """Format exception info"""
        if record.exc_info:
            return ''.join(traceback.format_exception(*record.exc_info))
        return None

    async def _save_to_db(self, log_data: Dict):
        """Async save to database"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    INSERT INTO logs
                    (timestamp, level, logger_name, message, module, function, line_number, exception)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    log_data['timestamp'],
                    log_data['level'],
                    log_data['logger_name'],
                    log_data['message'],
                    log_data['module'],
                    log_data['function'],
                    log_data['line_number'],
                    log_data['exception']
                ))
                await db.commit()
        except Exception as e:
            print(f"Failed to save log to database: {e}")


class VBotLogger:
    """VBot Advanced Logger with Telegram & SQL integration"""

    def __init__(self, name: str = "VBot", log_dir: str = "logs"):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        self.logger.handlers.clear()

        self.telegram_handler: Optional[TelegramLogHandler] = None
        self.sql_handler: Optional[SQLiteLogHandler] = None

        self._setup_file_handlers()
        self._setup_console_handler()

    def _setup_file_handlers(self):
        """Setup rotating file handlers"""

        # Main log (all levels)
        main_handler = RotatingFileHandler(
            self.log_dir / 'vbot.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.DEBUG)
        main_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s.%(funcName)s:%(lineno)d | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        main_handler.setFormatter(main_formatter)
        self.logger.addHandler(main_handler)

        # Error log (errors only)
        error_handler = RotatingFileHandler(
            self.log_dir / 'vbot_errors.log',
            maxBytes=5*1024*1024,  # 5MB
            backupCount=3,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)s | %(name)s.%(funcName)s:%(lineno)d\n'
            'Message: %(message)s\n'
            '%(pathname)s\n'
            '-' * 80,
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        error_handler.setFormatter(error_formatter)
        self.logger.addHandler(error_handler)

    def _setup_console_handler(self):
        """Setup console output"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '%(levelname)s | %(name)s | %(message)s'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)

    def setup_telegram_handler(self, client, log_group_id: int = LOG_GROUP_ID):
        """Setup Telegram log handler"""
        if self.telegram_handler:
            self.logger.removeHandler(self.telegram_handler)

        self.telegram_handler = TelegramLogHandler(client, log_group_id, level=logging.WARNING)

        telegram_formatter = logging.Formatter(
            '%(name)s.%(funcName)s:%(lineno)d\n%(message)s'
        )
        self.telegram_handler.setFormatter(telegram_formatter)
        self.telegram_handler.start()

        self.logger.addHandler(self.telegram_handler)
        self.logger.info(f"📱 Telegram logging enabled for group {log_group_id}")

    def setup_sql_handler(self, db_path: str = "data/logs.db"):
        """Setup SQL database log handler"""
        if self.sql_handler:
            self.logger.removeHandler(self.sql_handler)

        self.sql_handler = SQLiteLogHandler(db_path, level=logging.INFO)
        self.logger.addHandler(self.sql_handler)
        self.logger.info("🗄️ SQL logging enabled")

    def get_logger(self) -> logging.Logger:
        """Get logger instance"""
        return self.logger

    async def log_command(self,
                         user_id: int,
                         command: str,
                         success: bool = True,
                         execution_time: float = 0.0,
                         error: str = None):
        """Log command execution"""
        level = logging.INFO if success else logging.ERROR

        message = f"Command: {command} | User: {user_id} | Time: {execution_time:.3f}s"
        if error:
            message += f" | Error: {error}"

        self.logger.log(level, message)

    async def log_error(self,
                       error: Exception,
                       context: str = "",
                       user_id: int = None,
                       send_to_telegram: bool = True):
        """Log error with traceback"""
        error_msg = f"{context}: {str(error)}" if context else str(error)

        self.logger.error(
            error_msg,
            exc_info=True,
            extra={'user_id': user_id}
        )

        if send_to_telegram and self.telegram_handler:
            detailed_error = (
                f"**Error Context:** {context}\n"
                f"**User ID:** {user_id}\n"
                f"**Error Type:** {type(error).__name__}\n"
                f"**Error Message:** {str(error)}\n\n"
                f"**Traceback:**\n```\n"
                f"{''.join(traceback.format_tb(error.__traceback__))}\n```"
            )

            try:
                await self.telegram_handler.client.send_message(
                    LOG_GROUP_ID,
                    detailed_error[:4000]
                )
            except:
                pass

    async def log_startup(self, bot_info: Dict[str, Any]):
        """Log bot startup"""
        startup_msg = (
            f"🚀 **VBot Started**\n\n"
            f"👤 **User:** {bot_info.get('first_name', 'Unknown')}\n"
            f"🆔 **User ID:** {bot_info.get('user_id', 'Unknown')}\n"
            f"🕐 **Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )

        self.logger.info("VBot starting...")

        if self.telegram_handler:
            try:
                await self.telegram_handler.client.send_message(
                    LOG_GROUP_ID,
                    startup_msg
                )
            except:
                pass

    async def log_shutdown(self, reason: str = "Manual shutdown"):
        """Log bot shutdown"""
        shutdown_msg = (
            f"🛑 **VBot Stopped**\n\n"
            f"**Reason:** {reason}\n"
            f"**Time:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )

        self.logger.info(f"VBot shutting down: {reason}")

        if self.telegram_handler:
            try:
                await self.telegram_handler.client.send_message(
                    LOG_GROUP_ID,
                    shutdown_msg
                )
            except:
                pass

    def stop(self):
        """Stop all handlers"""
        if self.telegram_handler:
            self.telegram_handler.stop()

        for handler in self.logger.handlers:
            handler.close()

        self.logger.handlers.clear()


# Global logger instance
vbot_logger = VBotLogger("VBot")


def get_logger(name: str = "VBot") -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)


async def setup_logging(client):
    """Setup complete logging system"""
    # Setup Telegram handler
    vbot_logger.setup_telegram_handler(client, LOG_GROUP_ID)

    # Setup SQL handler
    vbot_logger.setup_sql_handler()

    logger = vbot_logger.get_logger()
    logger.info("✅ Logging system initialized")

    return vbot_logger
