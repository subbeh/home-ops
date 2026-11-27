# Vendored from https://github.com/mblauser/hermes-plugin-crawl4ai at 6eb0842 (MIT), reviewed before shipping.
# Changed here: provider.py reads through /crawl with stealth and retries a blocked read through Tavily.
"""Crawl4ai web extract plugin — standalone, auto-loaded."""

from __future__ import annotations


def register(ctx):
    """Register the Crawl4ai provider with the plugin context."""
    from .provider import Crawl4aiWebExtractProvider
    ctx.register_web_search_provider(Crawl4aiWebExtractProvider())