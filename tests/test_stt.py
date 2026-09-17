"""Определение контейнера аудио по сигнатуре (голосовые MAX ≠ OggOpus)."""
from app.services import stt


def test_detect_container_signatures():
    assert stt.detect_container(b"OggS" + b"\x00" * 20) == "ogg"
    assert stt.detect_container(b"ID3\x04" + b"\x00" * 20) == "mp3"
    assert stt.detect_container(b"\xff\xfb\x90\x00" + b"\x00" * 20) == "mp3"
    assert stt.detect_container(b"\x00\x00\x00\x18ftypM4A " + b"\x00" * 20) == "m4a"
    assert stt.detect_container(b"RIFF\x00\x00\x00\x00WAVEfmt ") == "wav"
    assert stt.detect_container(b"\x1a\x45\xdf\xa3" + b"\x00" * 20) == "webm"
    assert stt.detect_container(b"#!AMR\n") == "amr"
    assert stt.detect_container(b"\x00\x01\x02") == "unknown"
