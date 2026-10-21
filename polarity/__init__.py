"""Polarity: an AI lab partner for breadboard teaching labs.

Built for the Nebius x NVIDIA Global AI Hackathon (Physical AI track). The product name is
configured once as ``APP_NAME`` in :mod:`polarity.config`.

This package root deliberately imports nothing heavy so that the standalone Phase 0 script
(``scripts/verify_token_factory.py``) can import :mod:`polarity.verify` with only
openai, python-dotenv, pillow, numpy and rich installed.
"""

__version__ = "0.1.0"
