from datetime import datetime, timezone
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from httpx import ASGITransport, AsyncClient

from app.auth import auth_service, get_current_user, require_admin, require_employee
from app.database import get_db
from app.main import app
from app.models import User, UserRole
from app.schemas import UserRegisterRequest, UserResponse
from app.user_service import UserService, hash_password, verify_password


class FakeUserSession:
    def __init__(self, user=None):
        self.user = user
        self.added = []
        self.committed = False
        self.rolled_back = False

    async def scalar(self, _statement):
        return self.user

    def add(self, user):
        self.added.append(user)

    async def commit(self):
        self.committed = True
        if self.added:
            self.user = self.added[-1]

    async def refresh(self, user):
        user.id = 11
        user.created_at = datetime.now(timezone.utc)

    async def rollback(self):
        self.rolled_back = True


class InMemoryAuthSession(FakeUserSession):
    def __init__(self):
        super().__init__()
        self.users = {}
        self.next_id = 1

    async def scalar(self, statement):
        conditions = getattr(statement.whereclause, "clauses", [statement.whereclause])
        for condition in conditions:
            column = getattr(condition.left, "key", None)
            value = getattr(condition.right, "value", None)
            if column == "username":
                return next((user for user in self.users.values() if user.username == value), None)
            if column == "id":
                return self.users.get(value)
        return None

    async def commit(self):
        self.committed = True
        for user in self.added:
            user.id = self.next_id
            self.next_id += 1
            if user.is_active is None:
                user.is_active = True
            user.created_at = datetime.now(timezone.utc)
            self.users[user.id] = user

    async def refresh(self, _user):
        return None


@pytest.mark.asyncio
async def test_public_registration_always_creates_employee_and_hashes_password():
    db = FakeUserSession()
    request = UserRegisterRequest.model_validate({
        "username": "Alice",
        "password": "strong-password",
        "role": "admin",
    })

    user = await UserService(db).register_employee(request)

    assert user.username == "alice"
    assert user.role == UserRole.EMPLOYEE.value
    assert user.password_hash != request.password
    assert verify_password(request.password, user.password_hash)
    assert db.committed


@pytest.mark.asyncio
async def test_login_returns_same_error_for_unknown_account_and_wrong_password():
    db = FakeUserSession()
    service = UserService(db)

    with pytest.raises(HTTPException) as error:
        await service.authenticate("unknown", "bad-password")

    assert error.value.status_code == 401
    assert error.value.detail == "帳號或密碼錯誤"


@pytest.mark.asyncio
async def test_login_authenticates_employee_and_response_does_not_expose_hash():
    user = User(
        id=11,
        username="employee",
        password_hash=hash_password("strong-password"),
        role=UserRole.EMPLOYEE.value,
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    authenticated = await UserService(FakeUserSession(user)).authenticate(
        "employee", "strong-password"
    )

    response = UserResponse.model_validate(authenticated)
    assert response.role == UserRole.EMPLOYEE
    assert "password_hash" not in response.model_dump()


def test_roles_are_checked_from_current_user_record():
    employee = {"user_id": 2, "role": UserRole.EMPLOYEE.value}
    admin = {"user_id": 20, "role": UserRole.ADMIN.value}

    assert require_employee(employee) == employee
    assert require_admin(admin) == admin
    with pytest.raises(HTTPException) as error:
        require_admin(employee)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException) as error:
        require_employee(admin)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_token_role_claim_cannot_override_database_role():
    user = User(
        id=8,
        username="employee",
        password_hash="not-used",
        role=UserRole.EMPLOYEE.value,
        is_active=True,
    )
    db = FakeUserSession(user)
    forged_role_token = auth_service.create_access_token(8, {"role": "admin"})
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=forged_role_token)

    current_user = await get_current_user(credentials=credentials, db=db)

    assert current_user["role"] == UserRole.EMPLOYEE.value


@pytest.mark.asyncio
async def test_token_for_nonexistent_user_is_rejected():
    db = FakeUserSession()
    credentials = HTTPAuthorizationCredentials(
        scheme="Bearer", credentials=auth_service.create_access_token(999)
    )

    with pytest.raises(HTTPException) as error:
        await get_current_user(credentials=credentials, db=db)

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_disabled_user_cannot_login():
    user = User(
        id=12,
        username="disabled",
        password_hash=hash_password("strong-password"),
        role=UserRole.ADMIN.value,
        is_active=False,
    )

    with pytest.raises(HTTPException) as error:
        await UserService(FakeUserSession(user)).authenticate("disabled", "strong-password")

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_http_flow_register_login_me_and_reject_employee_admin_access():
    db = InMemoryAuthSession()

    async def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            registered = await client.post(
                "/auth/register",
                json={"username": "FlowUser", "password": "strong-password", "role": "admin"},
            )
            assert registered.status_code == 201
            assert registered.json()["role"] == "employee"
            assert "password_hash" not in registered.json()

            login = await client.post(
                "/auth/login", json={"username": "flowuser", "password": "strong-password"}
            )
            assert login.status_code == 200
            token = login.json()["access_token"]

            profile = await client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert profile.status_code == 200
            assert profile.json()["role"] == "employee"

            forbidden = await client.post(
                "/admin/orders/00000000-0000-0000-0000-000000000001/complete",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert forbidden.status_code == 403

            forbidden_menu_write = await client.post(
                "/admin/menus",
                json={"name": "Should not be created"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert forbidden_menu_write.status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
