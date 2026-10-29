"""Unit tests for Base62 encoding and Snowflake generator."""

import pytest

from src.url_shortener.infrastructure.encoding.base62 import (
    encode_base62,
    decode_base62,
    Base62CodeGenerator,
)


class TestBase62Encoding:
    def test_encode_decode_roundtrip(self) -> None:
        test_numbers = [0, 1, 61, 62, 123456, 987654321, 2**48 - 1]
        for num in test_numbers:
            encoded = encode_base62(num)
            decoded = decode_base62(encoded)
            assert decoded == num, f"Mismatch for {num}: encoded as {encoded}, got {decoded}"

    def test_negative_number_raises_error(self) -> None:
        with pytest.raises(ValueError):
            encode_base62(-1)

    def test_invalid_character_decode_raises_error(self) -> None:
        with pytest.raises(ValueError):
            decode_base62("abc@123")

    def test_empty_string_decode_raises_error(self) -> None:
        with pytest.raises(ValueError):
            decode_base62("")


class TestBase62Generator:
    def test_generates_unique_codes_high_volume(self) -> None:
        generator = Base62CodeGenerator(node_id=42)
        count = 10_000
        generated = {generator.generate_code() for _ in range(count)}
        # Zero collisions allowed
        assert len(generated) == count

    def test_code_meets_minimum_length(self) -> None:
        generator = Base62CodeGenerator(node_id=1)
        for _ in range(100):
            code = generator.generate_code(min_length=7)
            assert len(code) >= 7
