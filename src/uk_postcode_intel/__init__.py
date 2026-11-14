"""MCP server created with MCPize."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("uk-postcode-intel")
except PackageNotFoundError:  # running from source without `uv sync`
    __version__ = "0.0.0"
