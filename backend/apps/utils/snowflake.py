"""Snowflake ID generator.

64-bit ID layout:
| 1 bit sign | 41 bits timestamp (ms) | 10 bits machine_id | 12 bits sequence |

Supports 4096 IDs per millisecond per machine.
Epoch: 2024-01-01 00:00:00 UTC
"""

import time
import threading
import logging

# Epoch: 2024-01-01 00:00:00 UTC
EPOCH = 1704067200000

logger = logging.getLogger(__name__)

# Bit lengths
MACHINE_ID_BITS = 10
SEQUENCE_BITS = 12

# Max values
MAX_MACHINE_ID = (1 << MACHINE_ID_BITS) - 1  # 1023
MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

# Shifts
MACHINE_ID_SHIFT = SEQUENCE_BITS  # 12
TIMESTAMP_SHIFT = SEQUENCE_BITS + MACHINE_ID_BITS  # 22


class SnowflakeGenerator:
    """Thread-safe Snowflake ID generator."""

    def __init__(self, machine_id: int = 1):
        if machine_id < 0 or machine_id > MAX_MACHINE_ID:
            raise ValueError(
                f"machine_id must be between 0 and {MAX_MACHINE_ID}, got {machine_id}"
            )
        self.machine_id = machine_id
        self.sequence = 0
        self.last_timestamp = -1
        self._lock = threading.Lock()

    def _current_millis(self) -> int:
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp

    def generate(self) -> int:
        with self._lock:
            timestamp = self._current_millis()

            if timestamp < self.last_timestamp:
                logger.error(
                    "Clock moved backwards: last=%s now=%s (diff=%sms)",
                    self.last_timestamp, timestamp, self.last_timestamp - timestamp,
                )
                raise RuntimeError(
                    f"Clock moved backwards. Refusing to generate id for "
                    f"{self.last_timestamp - timestamp} milliseconds"
                )

            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & MAX_SEQUENCE
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                self.sequence = 0

            self.last_timestamp = timestamp

            return (
                ((timestamp - EPOCH) << TIMESTAMP_SHIFT)
                | (self.machine_id << MACHINE_ID_SHIFT)
                | self.sequence
            )


# Global singleton — machine_id=1 by default, can be overridden via env
_generator = SnowflakeGenerator(machine_id=1)


def snowflake_id() -> int:
    """Generate a new Snowflake ID."""
    return _generator.generate()
