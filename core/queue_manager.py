"""Message queue management - persists and recovers messages on bot crash"""
import json
import os
import asyncio
from datetime import datetime
from typing import List, Dict, Any


class MessageQueueManager:
    """Manages message queue for crash recovery"""

    QUEUE_FILE = os.path.join("logs", "files", "message_queue.json")

    def __init__(self):
        """Initialize queue manager"""
        os.makedirs(os.path.dirname(self.QUEUE_FILE), exist_ok=True)
        self.queue: List[Dict[str, Any]] = []
        self._load_queue_from_disk()

    def _load_queue_from_disk(self):
        """Load message queue from disk on startup"""
        if os.path.exists(self.QUEUE_FILE):
            try:
                with open(self.QUEUE_FILE, "r", encoding="utf-8") as f:
                    self.queue = json.load(f)
                print(f"📋 Queue Manager: Loaded {len(self.queue)} messages from disk")
            except Exception as e:
                print(f"⚠️ Queue Manager: Error loading queue: {e}")
                self.queue = []
        else:
            self.queue = []

    def _save_queue_to_disk(self):
        """Save message queue to disk"""
        try:
            with open(self.QUEUE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.queue, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Queue Manager: Error saving queue: {e}")

    def add_message(self, user_id: int, text: str, message_id: int = None, 
                    chat_id: int = None, username: str = None):
        """
        Add message to queue for processing.
        
        Args:
            user_id: Telegram user ID
            text: Message text
            message_id: Telegram message ID (optional)
            chat_id: Telegram chat ID (optional)
            username: User's username (optional)
        """
        msg_obj = {
            "timestamp": datetime.now().isoformat(),
            "user_id": user_id,
            "text": text,
            "message_id": message_id,
            "chat_id": chat_id,
            "username": username,
            "processed": False
        }
        self.queue.append(msg_obj)
        self._save_queue_to_disk()
        print(f"📥 Message added to queue (user:{user_id}) - Total: {len(self.queue)}")

    def get_pending_messages(self) -> List[Dict[str, Any]]:
        """Get all unprocessed messages"""
        return [msg for msg in self.queue if not msg.get("processed", False)]

    def mark_as_processed(self, user_id: int, text: str):
        """Mark a message as processed"""
        for msg in self.queue:
            if msg["user_id"] == user_id and msg["text"] == text and not msg.get("processed"):
                msg["processed"] = True
                self._save_queue_to_disk()
                break

    def clear_old_messages(self, days: int = 7):
        """Clear messages older than X days"""
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        original_len = len(self.queue)
        
        self.queue = [
            msg for msg in self.queue
            if datetime.fromisoformat(msg["timestamp"]) > cutoff_date
        ]
        
        if len(self.queue) < original_len:
            self._save_queue_to_disk()
            print(f"🗑️ Queue Manager: Cleaned {original_len - len(self.queue)} old messages")

    def clear_all(self):
        """Clear entire queue"""
        self.queue = []
        self._save_queue_to_disk()
        print("🗑️ Queue Manager: Queue cleared")

    def get_stats(self) -> Dict[str, int]:
        """Get queue statistics"""
        total = len(self.queue)
        processed = sum(1 for msg in self.queue if msg.get("processed"))
        pending = total - processed
        
        return {
            "total": total,
            "processed": processed,
            "pending": pending
        }


# Global queue manager instance
queue_manager = MessageQueueManager()


async def recover_queued_messages(message_handler_func, skip_first_n: int = 0):
    """
    Recover and process queued messages after bot restart.
    
    Args:
        message_handler_func: Async function to handle each message (takes user_id, text, username)
        skip_first_n: Skip first N messages (useful if you want to debug)
    """
    pending = queue_manager.get_pending_messages()
    
    if not pending:
        print("✅ No pending messages in queue")
        return

    print(f"🔄 Processing {len(pending)} queued messages...")
    
    for idx, msg in enumerate(pending[skip_first_n:], start=skip_first_n + 1):
        try:
            print(f"  [{idx}/{len(pending)}] Processing message from user {msg['user_id']}: {msg['text'][:50]}")
            
            # Call the message handler
            await message_handler_func(
                user_id=msg["user_id"],
                text=msg["text"],
                username=msg["username"]
            )
            
            # Mark as processed
            queue_manager.mark_as_processed(msg["user_id"], msg["text"])
            
            # Small delay to avoid flooding
            await asyncio.sleep(0.5)
            
        except Exception as e:
            print(f"  ❌ Error processing message: {e}")

    print("✅ Queue recovery complete!")
