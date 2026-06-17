"""MySQL 异步连接池，封装 aiomysql.Pool。

提供 DatabasePool 类用于管理 MySQL 连接池，以及全局单例 init_pool/get_pool。
用法：
    # 启动时初始化
    from app.core.database import init_pool, get_pool
    pool = init_pool(settings)
    await pool.init()

    # 请求处理中获取连接
    pool = get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT ...", (param,))
            rows = await cur.fetchall()

    # 关闭时释放
    await get_pool().close()
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

import aiomysql


class DatabasePool:
    """MySQL 异步连接池，封装 aiomysql.Pool。

    提供便捷方法 execute/fetch_all/fetch_one/fetch_val/execute_many，
    内部自动从连接池获取并归还连接。
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        db: str,
        minsize: int = 2,
        maxsize: int = 10,
        pool_recycle: int = 3600,
        connect_timeout: int = 10,
        read_timeout: int = 30,
        charset: str = "utf8mb4",
        autocommit: bool = True,
    ):
        self._config: dict[str, Any] = {
            "host": host,
            "port": port,
            "user": user,
            "password": password,
            "db": db,
            "minsize": minsize,
            "maxsize": maxsize,
            "pool_recycle": pool_recycle,
            "connect_timeout": connect_timeout,
            "read_timeout": read_timeout,
            "charset": charset,
            "autocommit": autocommit,
        }
        self._pool: aiomysql.Pool | None = None

    async def init(self) -> None:
        """创建连接池，应用启动时调用一次。"""
        self._pool = await aiomysql.create_pool(**self._config)

    async def close(self) -> None:
        """关闭连接池，应用关闭时调用。"""
        if self._pool is not None:
            self._pool.close()
            await self._pool.wait_closed()
            self._pool = None

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[aiomysql.Connection]:
        """获取一个连接的异步上下文管理器。

        用法：
            async with pool.acquire() as conn:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    await cur.execute(sql, params)
        """
        if self._pool is None:
            raise RuntimeError("Connection pool not initialized. Call init() first.")
        async with self._pool.acquire() as conn:
            yield conn

    async def execute(self, sql: str, params: tuple | list = ()) -> int:
        """执行写操作（INSERT/UPDATE/DELETE），返回 affected rows。"""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                return cur.rowcount

    async def fetch_all(self, sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
        """执行查询，返回 dict 列表。"""
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
                return rows  # type: ignore[return-value]

    async def fetch_one(self, sql: str, params: tuple | list = ()) -> dict[str, Any] | None:
        """执行查询，返回单行 dict 或 None。"""
        async with self.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
                return row  # type: ignore[return-value]

    async def fetch_val(self, sql: str, params: tuple | list = ()) -> Any:
        """执行查询，返回第一行第一列的值；无结果则返回 None。"""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, params)
                row = await cur.fetchone()
                return row[0] if row else None

    async def execute_many(self, sql: str, rows: list[tuple] | list[list]) -> int:
        """批量执行写操作，返回 affected rows。"""
        async with self.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(sql, rows)
                return cur.rowcount


# ---------------------------------------------------------------------------
# 全局单例
# ---------------------------------------------------------------------------

_pool: DatabasePool | None = None


def init_pool(settings) -> DatabasePool:
    """工厂函数：根据 Settings 创建全局 DatabasePool 单例。

    仅在首次调用时创建，重复调用返回已存在的实例。
    """
    global _pool
    if _pool is None:
        _pool = DatabasePool(
            host=settings.MYSQL_HOST,
            port=settings.MYSQL_PORT,
            user=settings.MYSQL_USER,
            password=settings.MYSQL_PASSWORD,
            db=settings.MYSQL_DATABASE,
            minsize=settings.MYSQL_POOL_MINSIZE,
            maxsize=settings.MYSQL_POOL_MAXSIZE,
            pool_recycle=settings.MYSQL_POOL_RECYCLE,
        )
    return _pool


def get_pool() -> DatabasePool:
    """获取全局连接池实例。

    如果尚未初始化则抛出 RuntimeError。
    """
    if _pool is None:
        raise RuntimeError("DatabasePool not initialized. Call init_pool() first.")
    return _pool
