"""Unit tests for lrc_client."""

import tempfile
import unittest
from pathlib import Path

from lrc_client import LyricLine, TrackResult, load_lrc, parse_lrc, sanitize_filename, save_lrc


class LrcClientTests(unittest.TestCase):
    def test_parse_lrc_handles_multiple_timestamps_and_sorts(self) -> None:
        raw = """
        [ti:Amor]
        [00:15.50]Segunda linea
        [00:05.25][00:25.00]Primera y tercera
        """
        parsed = parse_lrc(raw)
        self.assertEqual(
            parsed,
            [
                LyricLine(timestamp=5.25, text="Primera y tercera"),
                LyricLine(timestamp=15.50, text="Segunda linea"),
                LyricLine(timestamp=25.00, text="Primera y tercera"),
            ],
        )

    def test_sanitize_filename_strips_invalid_chars(self) -> None:
        self.assertEqual(sanitize_filename('AMOR: / \\ * ? " < > |'), "AMOR")

    def test_save_and_load_lrc_roundtrip(self) -> None:
        track = TrackResult(
            track_id=1,
            track_name="AMOR",
            artist_name="Emmanuel Cortes",
            album_name="Single",
            duration=180.0,
            synced_lyrics="[00:01.00]Mami, eres lo que quiero\n[00:04.50]Cuando veo tu sonrisa\n",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            saved = save_lrc(track, output_dir=Path(tmpdir))
            self.assertTrue(saved.is_file())
            loaded = load_lrc(saved)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].text, "Mami, eres lo que quiero")


if __name__ == "__main__":
    unittest.main()
