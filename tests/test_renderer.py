import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import renderer


class RendererInputTests(unittest.TestCase):
    @patch("renderer.time.sleep")
    @patch("renderer.run")
    def test_editor_input_uses_private_display(self, run, sleep):
        env = {**os.environ, "DISPLAY": ":88"}
        renderer.action({"type": "find_text", "path": "example.py", "text": "needle"}, env)
        self.assertTrue(run.called)
        self.assertTrue(all(call.kwargs.get("env") is env for call in run.call_args_list))


if __name__ == "__main__":
    unittest.main()
