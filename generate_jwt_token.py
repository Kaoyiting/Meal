"""
最小化JWT Token生成器
生成用戶和管理員的測試token
"""

import json
import base64
import hmac
import hashlib
from datetime import datetime, timedelta, timezone

def base64url_encode(data):
    """Base64URL編碼（移除padding）"""
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')

def create_jwt_token(user_id, hours=2):
    """
    生成JWT token
    
    Args:
        user_id (int): 用戶ID
        hours (int): 有效期小時數，預設2小時
    
    Returns:
        str: JWT token
    """
    # 使用與config.py相同的secret key
    secret_key = "your-jwt-secret-key-change-in-production"
    
    # JWT Header
    header = {"alg": "HS256", "typ": "JWT"}
    
    # JWT Payload
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(hours=hours)).timestamp()),
        "test": True
    }
    
    # 編碼header和payload
    header_encoded = base64url_encode(json.dumps(header, separators=(',', ':')).encode())
    payload_encoded = base64url_encode(json.dumps(payload, separators=(',', ':')).encode())
    
    # 創建簽名
    message = f"{header_encoded}.{payload_encoded}"
    signature = hmac.new(secret_key.encode(), message.encode(), hashlib.sha256).digest()
    signature_encoded = base64url_encode(signature)
    
    # 組合最終token
    return f"{message}.{signature_encoded}"

if __name__ == "__main__":
    print("=== 測試用JWT Token ===")
    
    # 生成用戶token (ID=123)
    user_token = create_jwt_token(123)
    print(f"\n用戶token (ID=123, 2小時有效):")
    print(f"Bearer {user_token}")
    
    # 生成管理員token (ID=1)
    admin_token = create_jwt_token(1)
    print(f"\n管理員token (ID=1, 2小時有效):")
    print(f"Bearer {admin_token}")
    
    print(f"\n使用方式:")
    print(f"在API請求的Header中加入: Authorization: Bearer <token>")