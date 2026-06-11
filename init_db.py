#!/usr/bin/env python3
"""
数据库初始化脚本 - 创建表 + 生成系统邀请码
无默认账户，所有用户通过邀请码自行注册
"""
import asyncio
import secrets
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import init_db


async def main():
    print("=== Questra-Search 数据库初始化 ===\n")

    # 初始化数据库
    print("[1/2] 创建表...")
    await init_db()
    print("  表创建完成（含增量迁移）")

    # 生成系统邀请码
    print("\n[2/2] 生成系统邀请码...")
    from app.config import DATABASE_PATH
    from aiosqlite import connect

    async with connect(DATABASE_PATH) as db:
        db.row_factory = __import__("aiosqlite").Row

        # 检查是否已有未使用的系统邀请码
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM invite_codes WHERE used_by IS NULL AND created_by IS NULL"
        )
        unused_count = (await cursor.fetchone())["cnt"]

        if unused_count >= 5:
            print(f"  已有 {unused_count} 个未使用的系统邀请码，跳过生成")
            # 显示现有邀请码
            cursor = await db.execute(
                "SELECT code FROM invite_codes WHERE used_by IS NULL AND created_by IS NULL"
            )
            rows = await cursor.fetchall()
            print("  现有邀请码:")
            for r in rows:
                print(f"    {r['code']}")
        else:
            # 生成 5 个系统邀请码（created_by = NULL 表示系统生成）
            codes = []
            for _ in range(5):
                code = secrets.token_urlsafe(8)[:10].upper()
                await db.execute(
                    "INSERT INTO invite_codes (code, created_by) VALUES (?, NULL)",
                    (code,)
                )
                codes.append(code)
            await db.commit()
            print(f"  已生成 {len(codes)} 个系统邀请码:")
            for c in codes:
                print(f"    {c}")
            print("\n  将以上邀请码分享给需要注册的用户")

    print("\n=== 初始化完成 ===")
    print("提示: 所有用户通过邀请码自行注册，无默认账户")


if __name__ == "__main__":
    asyncio.run(main())
