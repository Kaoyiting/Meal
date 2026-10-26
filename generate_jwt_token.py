"""使用已建立的帳密登入並輸出 JWT；不再自行簽發假使用者 token。"""

import asyncio
from getpass import getpass

from app import database
from app.auth import auth_service
from app.user_service import UserService


async def main() -> None:
    username = input("帳號: ").strip().lower()
    password = getpass("密碼: ")
    await database.init_database()
    try:
        async with database.async_session_maker() as db:
            user = await UserService(db).authenticate(username, password)
            token = auth_service.create_access_token(user.id)
            print(f"使用者：{user.username}（{user.role}）")
            print(f"Bearer {token}")
    finally:
        await database.close_database()


if __name__ == "__main__":
    asyncio.run(main())
