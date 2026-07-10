"""Windows asyncio compatibility for psycopg async pools.

Python imports this module automatically when the project root is on sys.path.
psycopg async connections require SelectorEventLoop on Windows.
"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
