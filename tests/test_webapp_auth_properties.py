"""
Property-based tests for WebApp Auth Service.

**Feature: cabinet-webapp, Property 1: InitData signature validation**
**Feature: cabinet-webapp, Property 2: Invalid signature rejection**
**Validates: Requirements 2.2, 2.3, 2.6**
"""
import hashlib
import hmac
import json
import time
from urllib.parse import quote, urlencode

import pytest
from hypothesis import given, settings, strategies as st

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.webapp_auth_service import (
    WebAppAuthService,
    InvalidSignatureError,
    ExpiredDataError,
    InvalidInitDataError,
)


# Test bot token for testing
TEST_BOT_TOKEN = "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"


def create_valid_init_data(
    bot_token: str,
    user_id: int,
    first_name: str = "Test",
    auth_date: int = None,
    extra_params: dict = None
) -> str:
    """
    Creates valid initData string with correct signature.
    
    This helper generates initData exactly as Telegram would,
    allowing us to test the validation logic.
    """
    if auth_date is None:
        auth_date = int(time.time())
    
    # Build user JSON
    user_data = {
        "id": user_id,
        "first_name": first_name,
        "language_code": "en"
    }
    
    # Build params dict
    params = {
        "user": json.dumps(user_data, separators=(',', ':')),
        "auth_date": str(auth_date),
    }
    
    if extra_params:
        params.update(extra_params)
    
    # Create data_check_string (sorted by key, joined with \n)
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(params.items())
    )
    
    # Generate secret key: HMAC-SHA256("WebAppData", bot_token)
    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256
    ).digest()
    
    # Generate hash: HMAC-SHA256(secret_key, data_check_string)
    hash_value = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256
    ).hexdigest()
    
    # Add hash to params
    params["hash"] = hash_value
    
    # URL-encode
    return urlencode(params)


class TestInitDataValidation:
    """
    **Feature: cabinet-webapp, Property 1: InitData signature validation**
    
    *For any* initData string with valid HMAC-SHA256 signature computed 
    using bot token, validation should succeed and return user data.
    
    **Validates: Requirements 2.2, 2.3**
    """
    
    @given(
        user_id=st.integers(min_value=1, max_value=10**12),
        first_name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=100)
    def test_valid_signature_accepted(self, user_id: int, first_name: str):
        """
        Property 1: Valid initData with correct signature should be accepted.
        
        For any user_id and first_name, if we generate initData with
        correct HMAC signature, validation should succeed.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        # Generate valid initData
        init_data = create_valid_init_data(
            bot_token=TEST_BOT_TOKEN,
            user_id=user_id,
            first_name=first_name
        )
        
        # Validate - should not raise
        result = service.validate_init_data(init_data)
        
        # Check user data is extracted correctly
        assert result["user"] is not None
        assert result["user"]["id"] == user_id
        assert result["user"]["first_name"] == first_name
        assert result["auth_date"] is not None
    
    @given(
        user_id=st.integers(min_value=1, max_value=10**12),
    )
    @settings(max_examples=100)
    def test_user_id_extracted_correctly(self, user_id: int):
        """
        Property 1 (continued): telegram_user_id should be correctly extracted.
        
        For any valid user_id, after validation it should be accessible
        in the result.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        init_data = create_valid_init_data(
            bot_token=TEST_BOT_TOKEN,
            user_id=user_id
        )
        
        result = service.validate_init_data(init_data)
        
        assert result["user"]["id"] == user_id


class TestInvalidSignatureRejection:
    """
    **Feature: cabinet-webapp, Property 2: Invalid signature rejection**
    
    *For any* initData string with tampered or invalid signature,
    validation should raise InvalidSignatureError.
    
    **Validates: Requirements 2.6**
    """
    
    @given(
        user_id=st.integers(min_value=1, max_value=10**12),
        tamper_byte=st.integers(min_value=0, max_value=255),
    )
    @settings(max_examples=100)
    def test_tampered_hash_rejected(self, user_id: int, tamper_byte: int):
        """
        Property 2: Tampered hash should be rejected.
        
        For any valid initData, if we modify the hash, validation should fail.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        # Generate valid initData
        init_data = create_valid_init_data(
            bot_token=TEST_BOT_TOKEN,
            user_id=user_id
        )
        
        # Tamper with the hash - replace last character
        tamper_char = hex(tamper_byte % 16)[2:]  # 0-f
        if init_data.endswith(tamper_char):
            tamper_char = hex((tamper_byte + 1) % 16)[2:]
        
        tampered_data = init_data[:-1] + tamper_char
        
        # Should raise InvalidSignatureError
        with pytest.raises(InvalidSignatureError):
            service.validate_init_data(tampered_data)
    
    @given(
        user_id=st.integers(min_value=1, max_value=10**12),
    )
    @settings(max_examples=100)
    def test_wrong_bot_token_rejected(self, user_id: int):
        """
        Property 2 (continued): initData signed with different bot token should be rejected.
        
        For any initData signed with one bot token, validation with
        a different token should fail.
        """
        # Sign with one token
        init_data = create_valid_init_data(
            bot_token=TEST_BOT_TOKEN,
            user_id=user_id
        )
        
        # Validate with different token
        service = WebAppAuthService(bot_token="different:token")
        
        with pytest.raises(InvalidSignatureError):
            service.validate_init_data(init_data)
    
    def test_missing_hash_rejected(self):
        """
        Property 2 (edge case): initData without hash should be rejected.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        # Create initData without hash
        params = {
            "user": json.dumps({"id": 123, "first_name": "Test"}),
            "auth_date": str(int(time.time())),
        }
        init_data = urlencode(params)
        
        with pytest.raises(InvalidInitDataError):
            service.validate_init_data(init_data)
    
    def test_empty_init_data_rejected(self):
        """
        Property 2 (edge case): Empty initData should be rejected.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        with pytest.raises(InvalidInitDataError):
            service.validate_init_data("")


class TestExpiredDataRejection:
    """
    Tests for expired initData rejection.
    """
    
    def test_expired_init_data_rejected(self):
        """
        initData older than 24 hours should be rejected.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        # Create initData with old auth_date (25 hours ago)
        old_auth_date = int(time.time()) - (25 * 3600)
        
        init_data = create_valid_init_data(
            bot_token=TEST_BOT_TOKEN,
            user_id=123456,
            auth_date=old_auth_date
        )
        
        with pytest.raises(ExpiredDataError):
            service.validate_init_data(init_data)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestJWTRoundTrip:
    """
    **Feature: cabinet-webapp, Property 3: JWT round-trip consistency**
    **Feature: cabinet-webapp, Property 4: JWT contains organizer_id**
    
    *For any* valid claims dictionary, encoding to JWT and decoding back
    should produce equivalent claims.
    
    **Validates: Requirements 2.5, 2.7**
    """
    
    @given(
        user_id=st.integers(min_value=1, max_value=10**12),
        organizer_id=st.integers(min_value=1, max_value=10**9),
        first_name=st.text(min_size=1, max_size=50).filter(lambda x: x.strip()),
        username=st.text(min_size=0, max_size=32).filter(lambda x: not x or x.isalnum()),
    )
    @settings(max_examples=100)
    def test_jwt_round_trip_preserves_data(
        self, 
        user_id: int, 
        organizer_id: int, 
        first_name: str,
        username: str
    ):
        """
        Property 3: JWT round-trip consistency.
        
        For any user data and organizer_id, creating a JWT and then
        decoding it should preserve all the original data.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        user_data = {
            "id": user_id,
            "first_name": first_name,
            "username": username if username else None,
        }
        
        # Create JWT
        token = service.create_jwt_token(
            user_data=user_data,
            organizer_id=organizer_id
        )
        
        # Decode JWT
        decoded = service.verify_jwt_token(token)
        
        # Verify round-trip consistency
        assert decoded["telegram_user_id"] == user_id
        assert decoded["organizer_id"] == organizer_id
        assert decoded["first_name"] == first_name
        assert decoded["sub"] == str(user_id)
    
    @given(
        organizer_id=st.integers(min_value=1, max_value=10**9),
    )
    @settings(max_examples=100)
    def test_jwt_contains_organizer_id(self, organizer_id: int):
        """
        Property 4: JWT contains organizer_id.
        
        For any successful authentication, the returned JWT token
        should contain organizer_id claim.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        user_data = {"id": 123456, "first_name": "Test"}
        
        # Create JWT
        token = service.create_jwt_token(
            user_data=user_data,
            organizer_id=organizer_id
        )
        
        # Decode and verify organizer_id is present
        decoded = service.verify_jwt_token(token)
        
        assert "organizer_id" in decoded
        assert decoded["organizer_id"] == organizer_id
    
    @given(
        contact_id=st.integers(min_value=1, max_value=10**9),
    )
    @settings(max_examples=100)
    def test_jwt_preserves_optional_contact_id(self, contact_id: int):
        """
        Property 3 (continued): Optional contact_id should be preserved.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        user_data = {"id": 123456, "first_name": "Test"}
        
        # Create JWT with contact_id
        token = service.create_jwt_token(
            user_data=user_data,
            organizer_id=1,
            contact_id=contact_id
        )
        
        # Decode and verify contact_id is preserved
        decoded = service.verify_jwt_token(token)
        
        assert decoded.get("contact_id") == contact_id
    
    def test_jwt_has_required_claims(self):
        """
        Property 4 (edge case): JWT should have all required claims.
        """
        service = WebAppAuthService(bot_token=TEST_BOT_TOKEN)
        
        user_data = {"id": 123456, "first_name": "Test"}
        
        token = service.create_jwt_token(
            user_data=user_data,
            organizer_id=42
        )
        
        decoded = service.verify_jwt_token(token)
        
        # Check required claims
        assert "sub" in decoded
        assert "organizer_id" in decoded
        assert "telegram_user_id" in decoded
        assert "iat" in decoded
        assert "exp" in decoded
        assert "iss" in decoded
        assert decoded["iss"] == "cupguide_webapp"
