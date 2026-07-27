from unittest.mock import MagicMock

import documentation_mcp


def test_reconfigure_stdio_calls_stream_reconfigure_with_utf8():
    stream = MagicMock()
    documentation_mcp._reconfigure_stdio(stream)
    stream.reconfigure.assert_called_once_with(encoding="utf-8")


def test_reconfigure_stdio_ignores_stream_without_reconfigure():
    documentation_mcp._reconfigure_stdio(object())
