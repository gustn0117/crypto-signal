"""
Supabase (PostgreSQL) 데이터베이스 연결 관리자
"""
from supabase import acreate_client, AsyncClient
from config import SUPABASE_URL, SUPABASE_KEY


class Database:
    def __init__(self):
        self._client: AsyncClient | None = None

    async def connect(self):
        self._client = await acreate_client(SUPABASE_URL, SUPABASE_KEY)

    async def close(self):
        self._client = None

    @property
    def client(self) -> AsyncClient:
        assert self._client is not None, "Database not connected"
        return self._client
