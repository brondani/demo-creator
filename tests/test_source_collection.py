import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from scripts import collect_debian_sources as collector


class SourceCollectionTests(unittest.TestCase):
    def test_inventory_and_verified_sources(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            manifest = root / "packages.tsv"
            manifest.write_text("installed\tffmpeg\t7:5.1.8-0+deb12u1\tffmpeg\t7:5.1.8-0+deb12u1\n"
                                "installed\tlibavcodec\t7:5.1.8-0+deb12u1\tffmpeg\t7:5.1.8-0+deb12u1\n"
                                "not-installed\tunused\t1.0\tunused\t1.0\n")
            packages = collector.sources(manifest.read_text())
            self.assertEqual(packages, [("ffmpeg", "7:5.1.8-0+deb12u1")])
            data = {"ffmpeg.dsc": b"source descriptor", "ffmpeg.tar.xz": b"source archive"}
            hashes = {name: hashlib.sha1(content).hexdigest() for name, content in data.items()}
            metadata = {
                "package": "ffmpeg",
                "version": "7:5.1.8-0+deb12u1",
                "result": [{"hash": digest} for digest in hashes.values()],
                "fileinfo": {hashes[name]: [{"name": name, "size": len(content), "archive_name": "debian"}]
                             for name, content in data.items()},
            }
            ports_hash = hashlib.sha1(b"ports descriptor").hexdigest()
            metadata["result"].append({"hash": ports_hash})
            metadata["fileinfo"][ports_hash] = [{"name": "ffmpeg.dsc", "size": 16,
                                                  "archive_name": "debian-ports"}]

            def response(url):
                if "/mr/package/" in url:
                    return io.BytesIO(json.dumps(metadata).encode())
                for name, digest in hashes.items():
                    if url.endswith("/" + digest):
                        return io.BytesIO(data[name])
                raise AssertionError(url)

            with patch.object(collector, "open_url", side_effect=response):
                collector.collect(packages[0], root)
            folder = root / "ffmpeg" / "7%3A5.1.8-0%2Bdeb12u1"
            self.assertEqual((folder / "ffmpeg.dsc").read_bytes(), data["ffmpeg.dsc"])
            self.assertEqual((folder / "ffmpeg.tar.xz").read_bytes(), data["ffmpeg.tar.xz"])

    def test_mismatched_download_does_not_pass(self):
        digest = hashlib.sha1(b"expected").hexdigest()
        metadata = {"package": "pkg", "version": "1.0", "result": [{"hash": digest}],
                    "fileinfo": {digest: [{"name": "pkg.dsc", "size": 8, "archive_name": "debian"}]}}

        def response(url):
            return io.BytesIO(json.dumps(metadata).encode() if "/mr/package/" in url else b"tampered")

        with tempfile.TemporaryDirectory() as temp, patch.object(collector, "open_url", side_effect=response):
            with self.assertRaisesRegex(ValueError, "integrity check"):
                collector.collect(("pkg", "1.0"), Path(temp))


if __name__ == "__main__":
    unittest.main()
