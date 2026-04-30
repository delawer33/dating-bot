from __future__ import annotations

from redis.asyncio import Redis


class CacheClient:
    def __init__(self, host: str, port: int) -> None:
        self._client = Redis(host=host, port=port, decode_responses=True)

    async def ping(self) -> bool:
        pong = await self._client.ping()
        return bool(pong)

    async def close(self) -> None:
        await self._client.aclose()

    def key(self, strategy: str, item_id: int) -> str:
        return f"{strategy}:item:{item_id}"

    def write_back_set_key(self) -> str:
        return "write-back:dirty-ids"

    async def get(self, key: str) -> str | None:
        return await self._client.get(key)

    async def set(self, key: str, value: str) -> None:
        await self._client.set(key, value)

    async def delete_prefix(self, prefix: str) -> None:
        cursor = 0
        pattern = f"{prefix}*"
        while True:
            cursor, keys = await self._client.scan(cursor=cursor, match=pattern, count=200)
            if keys:
                await self._client.delete(*keys)
            if cursor == 0:
                break

    async def add_dirty_id(self, item_id: int) -> None:
        await self._client.sadd(self.write_back_set_key(), item_id)

    async def pop_all_dirty_ids(self) -> list[int]:
        members = await self._client.smembers(self.write_back_set_key())
        if members:
            await self._client.delete(self.write_back_set_key())
        return [int(member) for member in members]
