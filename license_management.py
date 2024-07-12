import os
from typing import Optional

import aiohttp
import asyncpg


async def get_license_key(user_identifier: str) -> Optional[str]:
  """Get the license key for a user."""
  conn = await asyncpg.connect(os.environ["DATABASE_URL"])
  try:
    result = await conn.fetchrow(
        "SELECT license_key FROM users WHERE username = $1",
        user_identifier)
    return result["license_key"] if result else None
  finally:
    await conn.close()

async def verify_license(license_key: str, increment_usage = True) -> tuple[bool, int]:
    data = {
        'product_id': os.environ['GUMROAD_PRODUCT_ID'],
        'license_key': license_key,
        'increment_uses_count': increment_usage
    }
    async with aiohttp.ClientSession() as session, session.post('https://api.gumroad.com/v2/licenses/verify', data=data) as response:
        if response.status != 200:
            return False, 0  # or any indication of failure and zero uses
        license_info = await response.json()
        success = license_info.get('success', False)
        uses = license_info.get('uses', 0)
        return success and uses < int(os.environ['GUMROAD_MAX_USES']), uses

async def check_and_store_license_key(license_key: str, user_identifier: str) -> bool:
    """Store the license key for a user."""
    good, uses = await verify_license(license_key, increment_usage=False)
    if good:
      conn = await asyncpg.connect(os.environ["DATABASE_URL"])
      try:
          await conn.execute(
              "INSERT INTO users (username, license_key) VALUES ($1, $2)",
              user_identifier, license_key)
          return True
      finally:
          await conn.close()
    return False