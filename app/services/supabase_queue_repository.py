"""Queue operations via Supabase RPC to pgmq."""

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from loguru import logger
from supabase import Client

from app.integrations.supabase_config import SupabaseConfig


@dataclass
class QueueSendResult:
    """Result of sending a message to the queue."""

    message_id: int


@dataclass
class QueueMessage:
    """Normalized queue message from pgmq read."""

    message_id: int
    read_count: int
    enqueued_at: datetime
    payload: dict[str, Any]


@dataclass
class QueueAckResult:
    """Result of archiving a message."""

    archived: bool


class SupabaseQueueRepository:
    """
    Repository for pgmq queue operations via Supabase RPC.
    Uses pgmq schema (send, read, archive).
    """

    def __init__(self, client: Client, config: SupabaseConfig) -> None:
        self._client = client
        self._config = config

    def send(self, payload: dict[str, Any], delay_seconds: int = 0) -> QueueSendResult:
        """
        Send a message to the queue.
        Returns the message ID from pgmq.send.
        """
        try:
            resp = (
                self._client.schema("pgmq")
                .rpc(
                    "send",
                    {
                        "queue_name": self._config.queue_name,
                        "msg": payload,
                        "delay": delay_seconds,
                    },
                )
                .execute()
            )
        except Exception as e:
            logger.exception("supabase_queue_send_failed | queue={}", self._config.queue_name)
            raise

        data = resp.data
        if data is None or (isinstance(data, list) and len(data) == 0):
            raise RuntimeError("pgmq.send returned no message ID")

        msg_id = data[0] if isinstance(data, list) else data
        if isinstance(msg_id, dict):
            msg_id = msg_id.get("send", msg_id.get("msg_id"))

        return QueueSendResult(message_id=int(msg_id))

    def read(
        self,
        batch_size: int = 1,
        vt_seconds: int = 30,
    ) -> list[QueueMessage]:
        """
        Read messages from the queue with visibility timeout.
        Returns normalized list of QueueMessage.
        """
        try:
            resp = (
                self._client.schema("pgmq")
                .rpc(
                    "read",
                    {
                        "queue_name": self._config.queue_name,
                        "vt": vt_seconds,
                        "qty": batch_size,
                    },
                )
                .execute()
            )
        except Exception as e:
            logger.exception("supabase_queue_read_failed | queue={}", self._config.queue_name)
            raise

        data = resp.data
        if not data:
            return []

        rows = data if isinstance(data, list) else [data]
        messages: list[QueueMessage] = []
        for row in rows:
            if isinstance(row, dict):
                msg_id = row.get("msg_id", row.get("message_id"))
                read_ct = row.get("read_ct", row.get("read_count", 0))
                enqueued_at = row.get("enqueued_at")
                payload = row.get("message", row.get("payload", {}))
                if isinstance(payload, str):
                    payload = json.loads(payload) if payload else {}
                messages.append(
                    QueueMessage(
                        message_id=int(msg_id),
                        read_count=int(read_ct) if read_ct is not None else 0,
                        enqueued_at=datetime.fromisoformat(str(enqueued_at).replace("Z", "+00:00"))
                        if enqueued_at
                        else datetime.now(),
                        payload=payload if isinstance(payload, dict) else {},
                    )
                )
        return messages

    def archive(self, message_id: int) -> QueueAckResult:
        """
        Archive a message (acknowledge completion).
        Moves message from queue to archive table.
        """
        try:
            resp = (
                self._client.schema("pgmq")
                .rpc(
                    "archive",
                    {
                        "queue_name": self._config.queue_name,
                        "msg_id": message_id,
                    },
                )
                .execute()
            )
        except Exception as e:
            logger.exception(
                "supabase_queue_archive_failed | queue={} msg_id={}",
                self._config.queue_name,
                message_id,
            )
            raise

        data = resp.data
        archived = data is True or (isinstance(data, list) and len(data) > 0 and data[0] is True)
        if isinstance(data, list) and len(data) > 0 and isinstance(data[0], bool):
            archived = data[0]
        elif isinstance(data, bool):
            archived = data

        return QueueAckResult(archived=archived)
