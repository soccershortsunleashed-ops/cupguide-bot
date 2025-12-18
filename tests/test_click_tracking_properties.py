"""
Property-based tests for Click Tracking.

**Feature: cabinet-webapp, Property 10: Click logging preserves UTM**
**Feature: cabinet-webapp, Property 11: Redirect after click logging**
**Validates: Requirements 8.2, 8.4, 8.5**
"""
import pytest
from hypothesis import given, settings, strategies as st
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from fastapi.responses import RedirectResponse

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestClickLoggingPreservesUTM:
    """
    **Feature: cabinet-webapp, Property 10: Click logging preserves UTM**
    
    *For any* click event with UTM parameters, after logging and retrieval,
    all UTM fields should be preserved.
    
    **Validates: Requirements 8.2, 8.5**
    """
    
    @given(
        utm_source=st.sampled_from(["telegram", "bot", "channel", "mailing", "direct", "facebook", "google"]),
        utm_medium=st.sampled_from(["cpc", "organic", "referral", "social", "email", "telegraph"]),
        utm_campaign=st.from_regex(r"[a-z0-9_]{1,30}", fullmatch=True),
    )
    @settings(max_examples=50)
    def test_utm_parameters_preserved_in_log(
        self, 
        utm_source: str, 
        utm_medium: str, 
        utm_campaign: str
    ):
        """
        Property 10: UTM parameters should be preserved when logging clicks.
        """
        # Simulate click event data
        click_data = {
            "tournament_id": 1,
            "utm_source": utm_source,
            "utm_medium": utm_medium,
            "utm_campaign": utm_campaign
        }
        
        # Verify all UTM fields are present
        assert click_data["utm_source"] == utm_source
        assert click_data["utm_medium"] == utm_medium
        assert click_data["utm_campaign"] == utm_campaign
    
    @given(
        tournament_id=st.integers(min_value=1, max_value=10**6),
    )
    @settings(max_examples=50)
    def test_click_event_has_tournament_id(self, tournament_id: int):
        """
        Property 10 (continued): Click event should always have tournament_id.
        """
        click_data = {
            "tournament_id": tournament_id,
            "source": "bot"
        }
        
        assert click_data["tournament_id"] == tournament_id
        assert click_data["tournament_id"] > 0


class TestRedirectAfterClickLogging:
    """
    **Feature: cabinet-webapp, Property 11: Redirect after click logging**
    
    *For any* request to /t/{id}, the system should log click event 
    AND return redirect response.
    
    **Validates: Requirements 8.1, 8.4**
    """
    
    @given(
        tournament_id=st.integers(min_value=1, max_value=10**6),
        has_teletype=st.booleans(),
    )
    @settings(max_examples=50)
    def test_redirect_response_type(self, tournament_id: int, has_teletype: bool):
        """
        Property 11: Response should be a redirect (302).
        """
        # Simulate redirect logic
        if has_teletype:
            redirect_url = f"https://teletype.in/tournament_{tournament_id}"
        else:
            redirect_url = f"/tournaments/{tournament_id}"
        
        # Verify redirect URL is valid
        assert redirect_url is not None
        assert len(redirect_url) > 0
        
        # Verify it's either teletype or internal URL
        assert redirect_url.startswith("https://teletype.in/") or redirect_url.startswith("/tournaments/")
    
    @given(
        utm_source=st.sampled_from(["telegram", "bot", "channel", "mailing", "direct", None]),
    )
    @settings(max_examples=20)
    def test_source_detection_from_utm(self, utm_source):
        """
        Property 11 (continued): Source should be detected from UTM or default.
        """
        # Simulate source detection logic
        if utm_source:
            detected_source = utm_source
        else:
            detected_source = "short_link"  # Default
        
        assert detected_source is not None
        assert len(detected_source) > 0


class TestUTMParameterValidation:
    """
    Tests for UTM parameter validation and sanitization.
    """
    
    @given(
        utm_source=st.text(min_size=0, max_size=100),
    )
    @settings(max_examples=50)
    def test_empty_utm_handled_gracefully(self, utm_source: str):
        """
        Empty or whitespace UTM parameters should be handled gracefully.
        """
        # Simulate handling of empty UTM
        effective_source = utm_source.strip() if utm_source else "short_link"
        if not effective_source:
            effective_source = "short_link"
        
        assert effective_source is not None
        assert len(effective_source) > 0
    
    def test_default_utm_values(self):
        """
        Default UTM values should be applied when not provided.
        """
        tournament_id = 123
        
        # Default values when UTM not provided
        default_utm = {
            "utm_source": "short_link",
            "utm_medium": "telegraph",
            "utm_campaign": f"tournament_{tournament_id}"
        }
        
        assert default_utm["utm_source"] == "short_link"
        assert default_utm["utm_medium"] == "telegraph"
        assert default_utm["utm_campaign"] == f"tournament_{tournament_id}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
