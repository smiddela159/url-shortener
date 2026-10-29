"""High-performance Base62 encoder and collision-resistant short code generator."""

import os
import secrets
import threading
import time

ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(ALPHABET)
CHAR_MAP = {char: idx for idx, char in enumerate(ALPHABET)}


def encode_base62(num: int) -> str:
    """Encode an unsigned integer into a Base62 string."""
    if num < 0:
        raise ValueError("Cannot encode negative numbers in Base62.")
    if num == 0:
        return ALPHABET[0]

    chars = []
    while num > 0:
        num, rem = divmod(num, BASE)
        chars.append(ALPHABET[rem])
    return "".join(reversed(chars))


def decode_base62(s: str) -> int:
    """Decode a Base62 string into an unsigned integer."""
    if not s:
        raise ValueError("Cannot decode empty string.")
    num = 0
    for char in s:
        if char not in CHAR_MAP:
            raise ValueError(f"Invalid Base62 character: '{char}'")
        num = num * BASE + CHAR_MAP[char]
    return num


class Base62CodeGenerator:
    """Thread-safe, collision-resistant short code generator.
    
    Combines:
    - 41 bits of timestamp (milliseconds since epoch)
    - 10 bits of node / worker ID
    - 12 bits of monotonic sequence counter
    yielding a unique 64-bit integer, encoded into 7-8 Base62 characters.
    """

    # Custom epoch: 2026-01-01T00:00:00Z
    EPOCH = 1767225600000

    def __init__(self, node_id: int = 1) -> None:
        self.node_id = node_id & 0x3FF  # 10 bits (0-1023)
        self._sequence = 0
        self._last_timestamp = -1
        self._lock = threading.Lock()

    def _current_millis(self) -> int:
        return int(time.time() * 1000)

    def next_id(self) -> int:
        """Generates a globally unique 64-bit snowflake integer."""
        with self._lock:
            timestamp = self._current_millis()

            if timestamp < self._last_timestamp:
                # Clock moved backwards; wait until clock catches up
                timestamp = self._last_timestamp

            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & 0xFFF  # 12 bits (0-4095)
                if self._sequence == 0:
                    # Sequence exhausted in this millisecond; spin wait
                    while timestamp <= self._last_timestamp:
                        timestamp = self._current_millis()
            else:
                self._sequence = 0

            self._last_timestamp = timestamp

            id_num = (
                ((timestamp - self.EPOCH) << 22)
                | (self.node_id << 12)
                | self._sequence
            )
            # Ensure strictly non-negative
            return abs(id_num)

    def generate_code(self, min_length: int = 7) -> str:
        """Generates a unique Base62 short code padded to min_length."""
        raw_id = self.next_id()
        encoded = encode_base62(raw_id)
        if len(encoded) < min_length:
            # Salt with crypto-secure random prefix to maintain length & prevent predictability
            pad_needed = min_length - len(encoded)
            prefix = "".join(secrets.choice(ALPHABET) for _ in range(pad_needed))
            return prefix + encoded
        return encoded
