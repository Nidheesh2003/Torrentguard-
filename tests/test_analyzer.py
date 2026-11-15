import unittest

from app import BencodeError, analyze_torrent, decode_bencode


def bencode(value):
    if isinstance(value, int):
        return b"i" + str(value).encode() + b"e"
    if isinstance(value, bytes):
        return str(len(value)).encode() + b":" + value
    if isinstance(value, list):
        return b"l" + b"".join(bencode(item) for item in value) + b"e"
    if isinstance(value, dict):
        return b"d" + b"".join(bencode(k) + bencode(v) for k, v in sorted(value.items())) + b"e"
    raise TypeError(type(value))


class BencodeTests(unittest.TestCase):
    def test_decode_simple_dictionary(self):
        self.assertEqual(decode_bencode(b"d1:ai1ee"), {b"a": 1})

    def test_reject_invalid_data(self):
        with self.assertRaises(BencodeError):
            decode_bencode(b"not bencode")

    def test_detect_executable_extension(self):
        raw = bencode({
            b"announce": b"https://tracker.example/announce",
            b"info": {
                b"name": b"demo",
                b"files": [
                    {b"length": 123, b"path": [b"setup.exe"]}
                ],
                b"piece length": 16384,
                b"pieces": b"x" * 20
            }
        })
        report = analyze_torrent("demo.torrent", raw)
        self.assertEqual(report["file_count"], 1)
        self.assertGreaterEqual(report["risk_score"], 20)
        self.assertTrue(any("setup.exe" in flag["title"] for flag in report["flags"]))


if __name__ == "__main__":
    unittest.main()
