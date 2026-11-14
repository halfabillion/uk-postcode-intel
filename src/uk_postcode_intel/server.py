"""MCP server entry point."""

import contextlib
import json
import logging
import signal
import time
from os import getenv

from fastmcp import FastMCP
from fastmcp.server.middleware import Middleware, MiddlewareContext
from rich.console import Console
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .full_report import full_area_intelligence
from .tools import (
    area_report,
    crime_summary,
    flood_warnings,
    food_hygiene_nearby,
    house_prices,
    postcode_lookup,
)

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=getenv("LOG_LEVEL", "INFO"),
)

# ============================================================================
# Dev Logging Middleware
# ============================================================================

console = Console()
IS_DEV = getenv("ENV", "development") != "production"


def truncate(s: str, max_len: int = 60) -> str:
    """Truncate string with ellipsis."""
    return s if len(s) <= max_len else s[: max_len - 3] + "..."


def format_latency(ms: float) -> str:
    """Color-code latency: green <100ms, yellow 100-500ms, red >500ms."""
    if ms < 100:
        return f"[green]{ms:.0f}ms[/green]"
    if ms < 500:
        return f"[yellow]{ms:.0f}ms[/yellow]"
    return f"[red]{ms:.0f}ms[/red]"


def timestamp() -> str:
    """Get current time as HH:MM:SS."""
    return time.strftime("%H:%M:%S")


class DevLoggingMiddleware(Middleware):
    """Colorized dev logging middleware for MCP requests/responses."""

    async def on_message(self, context: MiddlewareContext, call_next):
        """Log all MCP messages with timing."""
        if not IS_DEV:
            return await call_next(context)

        method = context.method
        message = context.message

        # Skip noisy notifications (FastMCP 4 routes every inbound message here)
        if context.type == "notification":
            return await call_next(context)

        # Log request
        if method == "tools/call" and message:
            tool_name = getattr(message, "name", "unknown")
            tool_args = getattr(message, "arguments", {})
            args_str = truncate(json.dumps(tool_args)) if tool_args else ""
            console.print(
                f"[dim][{timestamp()}][/dim] [cyan]→[/cyan] tools/call [bold]{tool_name}[/bold]"
                + (f" [dim]{args_str}[/dim]" if args_str else "")
            )
        else:
            params_str = ""
            if message:
                with contextlib.suppress(Exception):
                    if hasattr(message, "model_dump"):
                        message = message.model_dump(mode="json", by_alias=True, exclude_none=True)
                    if message:
                        params_str = f" [dim]{truncate(json.dumps(message, default=str))}[/dim]"
            console.print(f"[dim][{timestamp()}][/dim] [cyan]→[/cyan] {method}{params_str}")

        # Execute and time. Tool errors and validation failures are raised as
        # exceptions, so log them here and re-raise to let FastMCP report them.
        start = time.time()
        try:
            result = await call_next(context)
        except Exception as e:
            latency = format_latency((time.time() - start) * 1000)
            error_msg = truncate(" ".join(f"{type(e).__name__}: {e}".split()))
            console.print(
                f"[dim][{timestamp()}][/dim] [red]✖[/red] {method}"
                f" [red]{error_msg}[/red] ({latency})"
            )
            raise
        latency_ms = (time.time() - start) * 1000

        # Log response
        latency = format_latency(latency_ms)

        if getattr(result, "is_error", False):
            error_msg = truncate(str(result))
            console.print(
                f"[dim][{timestamp()}][/dim] [red]✖[/red] {method}"
                f" [red]{error_msg}[/red] ({latency})"
            )
        elif method == "tools/call":
            # Extract tool result for display
            try:
                content = getattr(result, "content", [])
                if content and hasattr(content[0], "text"):
                    result_text = truncate(content[0].text)
                    console.print(
                        f"[dim][{timestamp()}][/dim] [green]←[/green] {result_text} ({latency})"
                    )
                else:
                    console.print(
                        f"[dim][{timestamp()}][/dim] [green]✓[/green] tools/call ({latency})"
                    )
            except Exception:
                console.print(f"[dim][{timestamp()}][/dim] [green]✓[/green] tools/call ({latency})")
        else:
            console.print(f"[dim][{timestamp()}][/dim] [green]✓[/green] {method} ({latency})")

        return result


# ============================================================================
# MCP Server Setup
# ============================================================================

# version is reported as serverInfo.version (FastMCP's own version if omitted)
mcp = FastMCP("uk-postcode-intel", version=__version__)

# Add dev logging middleware
mcp.add_middleware(DevLoggingMiddleware())


# Health endpoint
@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy"})


# Register tools
for _t in (full_area_intelligence, area_report, postcode_lookup, crime_summary, flood_warnings,
           food_hygiene_nearby, house_prices):
    mcp.tool()(_t)


def main() -> None:
    """Run the MCP server with graceful shutdown."""
    port = int(getenv("PORT", "8080"))

    console.print()
    console.print("[bold]MCP Server running on[/bold]", f"[cyan]http://localhost:{port}[/cyan]")
    console.print(f"  [dim]Health:[/dim] http://localhost:{port}/health")
    console.print(f"  [dim]MCP:[/dim]    http://localhost:{port}/mcp")

    if IS_DEV:
        console.print()
        console.print("[dim]" + "─" * 50 + "[/dim]")
        console.print()

    def handle_sigterm(*_):
        console.print("[dim]Received SIGTERM, shutting down...[/dim]")
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    mcp.run(
        transport="http",  # Streamable HTTP, served at /mcp
        host="0.0.0.0",
        port=port,
        show_banner=False,  # we print our own banner above
    )


if __name__ == "__main__":
    main()
