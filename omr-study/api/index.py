"""Vercel ASGI entry point; frontend assets are served by Vercel's CDN."""

from backend.main import app

__all__ = ["app"]
