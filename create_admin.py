"""互動式建立第一個管理員：python create_admin.py"""

import asyncio
from getpass import getpass

from app import database
from app.schemas import UserRegisterRequest
from app.user_service import UserService


async def main() -> None:
    username = input("管理員帳號（3-50 個英數字、_、. 或 -）: ").strip()
    password = getpass("管理員密碼（至少 8 個字元）: ")
    confirmation = getpass("再次輸入密碼: ")
    if password != confirmation:
        raise SystemExit("兩次密碼不一致")

    request = UserRegisterRequest(username=username, password=password)
    await database.init_database()
    try:
        async with database.async_session_maker() as db:
            user = await UserService(db).create_admin(request)
            print(f"管理員已建立：{user.username}（role={user.role}）")
    finally:
        await database.close_database()


if __name__ == "__main__":
    asyncio.run(main())
