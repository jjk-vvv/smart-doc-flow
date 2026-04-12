from __future__ import annotations

import sys
import time
from pathlib import Path


MODULE2_ROOT = Path(__file__).resolve().parents[1]
if str(MODULE2_ROOT) not in sys.path:
    sys.path.insert(0, str(MODULE2_ROOT))

from app.assistant_1.streaming import Assistant1TextBuffer


# ---------------------------------------------------------------------------
# should_flush — length threshold
# ---------------------------------------------------------------------------

def test_flush_when_length_exceeds_threshold() -> None:
    buf = Assistant1TextBuffer(flush_chars=10, flush_timeout_ms=99999)
    buf.append("A" * 11, now_monotonic=1.0)
    assert buf.should_flush(1.0) is True


def test_no_flush_when_below_threshold_and_no_timeout() -> None:
    buf = Assistant1TextBuffer(flush_chars=36, flush_timeout_ms=99999)
    buf.append("short", now_monotonic=1.0)
    assert buf.should_flush(1.001) is False


# ---------------------------------------------------------------------------
# should_flush — punctuation triggers
# ---------------------------------------------------------------------------

def test_flush_on_chinese_period() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("结论如下。", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


def test_flush_on_chinese_exclamation() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("非常好！", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


def test_flush_on_chinese_question() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("是吗？", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


def test_flush_on_chinese_semicolon() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("先说这个；", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


def test_flush_on_newline_not_triggered_by_stripped_text() -> None:
    # The buffer checks stripped.endswith(...), so a trailing newline is stripped away
    # and does NOT trigger punctuation flush on its own — it needs content length or timeout
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("第一行内容\n", now_monotonic=1.0)
    # stripped = "第一行内容" — doesn't end with \n after strip()
    # content length 5 chars < 999 → no flush without timeout
    assert buf.should_flush(1.001) is False


def test_flush_on_english_period() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("Done.", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


def test_flush_on_english_exclamation() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("Great!", now_monotonic=1.0)
    assert buf.should_flush(1.001) is True


# ---------------------------------------------------------------------------
# should_flush — timeout
# ---------------------------------------------------------------------------

def test_flush_on_timeout() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=50)
    buf.append("abc", now_monotonic=0.0)
    # Simulate 60ms elapsed (0.060 seconds)
    assert buf.should_flush(0.060) is True


def test_no_flush_before_timeout() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=1000)
    buf.append("abc", now_monotonic=0.0)
    assert buf.should_flush(0.010) is False  # only 10ms elapsed


# ---------------------------------------------------------------------------
# should_flush — empty buffer never flushes
# ---------------------------------------------------------------------------

def test_no_flush_on_empty_buffer() -> None:
    buf = Assistant1TextBuffer(flush_chars=1, flush_timeout_ms=1)
    assert buf.should_flush(9999.0) is False


def test_no_flush_on_whitespace_only_buffer() -> None:
    buf = Assistant1TextBuffer(flush_chars=1, flush_timeout_ms=1)
    buf.append("   ", now_monotonic=0.0)
    assert buf.should_flush(9999.0) is False


# ---------------------------------------------------------------------------
# force=True
# ---------------------------------------------------------------------------

def test_force_flush_even_when_short() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    buf.append("hi", now_monotonic=1.0)
    assert buf.should_flush(1.001, force=True) is True


def test_force_flush_empty_returns_false() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=99999)
    assert buf.should_flush(1.0, force=True) is False


# ---------------------------------------------------------------------------
# pop() — returns and clears
# ---------------------------------------------------------------------------

def test_pop_returns_full_text_and_clears() -> None:
    buf = Assistant1TextBuffer()
    buf.append("hello", now_monotonic=1.0)
    buf.append(" world", now_monotonic=1.1)
    result = buf.pop()
    assert result == "hello world"
    assert buf.text == ""
    assert buf.should_flush(9999.0) is False


# ---------------------------------------------------------------------------
# append() — accumulates monotonic
# ---------------------------------------------------------------------------

def test_append_updates_monotonic_time() -> None:
    buf = Assistant1TextBuffer(flush_chars=999, flush_timeout_ms=100)
    buf.append("first", now_monotonic=1.0)
    buf.append("second", now_monotonic=2.0)
    # last_append_monotonic should be 2.0 now
    # 50ms after last append → not timed out (timeout is 100ms)
    assert buf.should_flush(2.050) is False
    # 110ms after last append → timed out
    assert buf.should_flush(2.110) is True


# ---------------------------------------------------------------------------
# high-verbosity flush_chars=52
# ---------------------------------------------------------------------------

def test_high_verbosity_flush_chars_higher_threshold() -> None:
    buf = Assistant1TextBuffer(flush_chars=52, flush_timeout_ms=99999)
    buf.append("A" * 40, now_monotonic=1.0)
    # 40 < 52, no sentence end, no timeout → should NOT flush
    assert buf.should_flush(1.001) is False
    buf.append("B" * 13, now_monotonic=1.002)
    # now 53 chars ≥ 52 → should flush
    assert buf.should_flush(1.003) is True
