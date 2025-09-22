from enum import Enum, auto
from typing import TypedDict
from dataclasses import dataclass
import threading
import time
from collections import deque

class StatusCode(Enum):
    """Possible internal states of an exposed database"""
    FREE = auto()
    FOLLOWER_CHANGE = auto()
    DATABASE_CHANGE = auto()

class ReturnCode(Enum):
    """Possible remote requests return codes"""
    OK = auto()
    ERROR = auto()
    BANNED = auto()

class Operation(str, Enum):
    """Available operations on an exposed database"""
    ADD_ENTRY = "add_entry"
    ADD_GROUP = "add_group"
    DELETE_ENTRY = "remove_entry"
    DELETE_GROUP = "update_group"

@dataclass
class Notification():
    """Data that composes a notification"""
    message: str
    timestamp: float
    proposition_id: int
    db_id: int

class AddEntryData(TypedDict):
    """Data necessary to add an entry to an exposed database"""
    destination_group: list[str]
    title: str
    username: str
    passwd: str

class AddGroupData(TypedDict):
    """Data necessary to add a group to an exposed database"""
    parent_group: list[str]
    group_name: str

class DeleteEntryData(TypedDict):
    """Data necessary to delete an entry of an exposed database"""
    entry_path: list[str]

class DeleteGroupData(TypedDict):
    """Data necessary to delete a group of an exposed database"""
    path: list[str]

# A more concise representation of the possible data type for the database operatiosn
OperationData = AddEntryData | AddGroupData | DeleteEntryData | DeleteGroupData

class NotificationQueue:
    def __init__(self):
        self._queue = deque()
        self._lock = threading.Lock()

    def push(self, notification: Notification) -> None:
        """Push a new notification (top of stack)."""
        with self._lock:
            self._queue.appendleft(notification)

    def pop(self) -> Notification | None:
        """Pop most recent notification, or None if empty."""
        with self._lock:
            if self._queue:
                return self._queue.popleft()
            return None

    def remove_expired(self) -> None:
        """Remove expired notifications."""
        now = time.time()
        with self._lock:
            self._queue = deque(
                n for n in self._queue if (now - n.timestamp) <= 30
            )

    def remove_at(self, index: int) -> bool:
        """Remove notification at given index. Returns True if successful."""
        with self._lock:
            if 0 <= index < len(self._queue):
                del self._queue[index]
                return True
            return False
        
    def get_all(self) -> list[Notification]:
        """Return a snapshot of all notifications."""
        with self._lock:
            return list(self._queue)

    def __len__(self) -> int:
        with self._lock:
            return len(self._queue)

    def __iter__(self):
        """Safe iterator: it's a snapshot copy to free the lock rapidly."""
        with self._lock:
            return iter(list(self._queue))
