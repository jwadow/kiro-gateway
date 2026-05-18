# -*- coding: utf-8 -*-

"""
Tests for kiro/account_errors.py - Error classification for failover logic.

Tests the classify_error() function that determines whether an error is:
- FATAL: Error in the request itself → return to client immediately
- RECOVERABLE: Error with the account → try next account
"""

import pytest
from kiro.account_errors import classify_error, ErrorType


class TestClassifyErrorRecoverable:
    """
    Tests for RECOVERABLE errors (account-specific issues).
    
    These errors should trigger failover to the next account.
    """
    
    def test_classify_error_402_recoverable(self):
        """
        Test that 402 (payment required) is classified as RECOVERABLE.
        
        What it does: Verifies 402 status code classification
        Purpose: Monthly quota exceeded should trigger account failover
        """
        print("\n=== Test: 402 Payment Required → RECOVERABLE ===")
        
        # Act
        result = classify_error(status_code=402, reason="MONTHLY_REQUEST_COUNT")
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.RECOVERABLE, "402 should be RECOVERABLE (quota exceeded)"
    
    def test_classify_error_402_no_reason_recoverable(self):
        """
        Test that 402 without reason is still RECOVERABLE.
        
        What it does: Verifies 402 classification regardless of reason
        Purpose: Any payment issue is account-specific
        """
        print("\n=== Test: 402 without reason → RECOVERABLE ===")
        
        # Act
        result = classify_error(status_code=402, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.RECOVERABLE, "402 should always be RECOVERABLE"
    
    def test_classify_error_403_recoverable(self):
        """
        Test that 403 (token expired) is classified as RECOVERABLE.
        
        What it does: Verifies 403 status code classification
        Purpose: Token expiration is account-specific, should try next account
        """
        print("\n=== Test: 403 Forbidden → RECOVERABLE ===")
        
        # Act
        result = classify_error(status_code=403, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.RECOVERABLE, "403 should be RECOVERABLE (token expired)"
    
    def test_classify_error_429_recoverable(self):
        """
        Test that 429 (rate limit) is classified as RECOVERABLE.
        
        What it does: Verifies 429 status code classification
        Purpose: Rate limit is account-specific, should try next account
        """
        print("\n=== Test: 429 Rate Limit → RECOVERABLE ===")
        
        # Act
        result = classify_error(status_code=429, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.RECOVERABLE, "429 should be RECOVERABLE (rate limit)"


class TestClassifyErrorFatal:
    """
    Tests for FATAL errors (request-specific issues).
    
    These errors should be returned to client immediately without failover.
    """
    
    def test_classify_error_400_content_length_fatal(self):
        """
        Test that 400 + CONTENT_LENGTH_EXCEEDS_THRESHOLD is FATAL.
        
        What it does: Verifies context overflow classification
        Purpose: Context overflow will fail on all accounts
        """
        print("\n=== Test: 400 + CONTENT_LENGTH_EXCEEDS_THRESHOLD → FATAL ===")
        
        # Act
        result = classify_error(
            status_code=400,
            reason="CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        )
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "Context overflow should be FATAL"
    
    def test_classify_error_400_null_reason_fatal(self):
        """
        Test that 400 + reason=None is FATAL.
        
        What it does: Verifies generic bad request classification
        Purpose: "Improperly formed request" is request issue, not account issue
        """
        print("\n=== Test: 400 + reason=None → FATAL ===")
        
        # Act
        result = classify_error(status_code=400, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "400 with null reason should be FATAL"
    
    def test_classify_error_400_unknown_reason_fatal(self):
        """
        Test that 400 + unknown reason is FATAL.
        
        What it does: Verifies unknown 400 reason classification
        Purpose: Unknown validation errors are request issues
        """
        print("\n=== Test: 400 + unknown reason → FATAL ===")
        
        # Act
        result = classify_error(status_code=400, reason="UNKNOWN_VALIDATION_ERROR")
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "400 with unknown reason should be FATAL"
    
    def test_classify_error_422_fatal(self):
        """
        Test that 422 (validation error) is FATAL.
        
        What it does: Verifies 422 status code classification
        Purpose: Validation errors are request issues, not account issues
        """
        print("\n=== Test: 422 Validation Error → FATAL ===")
        
        # Act
        result = classify_error(status_code=422, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "422 should be FATAL (validation error)"
    
    def test_classify_error_500_fatal(self):
        """
        Test that 500 (server error) is FATAL.
        
        What it does: Verifies 5xx status code classification
        Purpose: Kiro API server errors won't be fixed by trying another account
        """
        print("\n=== Test: 500 Server Error → FATAL ===")
        
        # Act
        result = classify_error(status_code=500, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "500 should be FATAL (server error)"
    
    def test_classify_error_503_fatal(self):
        """
        Test that 503 (service unavailable) is FATAL.
        
        What it does: Verifies 503 status code classification
        Purpose: Service unavailable affects all accounts
        """
        print("\n=== Test: 503 Service Unavailable → FATAL ===")
        
        # Act
        result = classify_error(status_code=503, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "503 should be FATAL (service unavailable)"


class TestClassifyErrorEdgeCases:
    """
    Tests for edge cases and unknown error codes.
    """
    
    def test_classify_error_unknown_status_fatal(self):
        """
        Test that unknown status codes default to FATAL.
        
        What it does: Verifies default classification for unknown codes
        Purpose: Conservative approach - don't waste retries on unknown errors
        """
        print("\n=== Test: Unknown status code → FATAL ===")
        
        # Act
        result = classify_error(status_code=418, reason=None)  # I'm a teapot
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "Unknown status codes should default to FATAL"
    
    def test_classify_error_401_fatal(self):
        """
        Test that 401 (unauthorized) is FATAL.
        
        What it does: Verifies 401 classification
        Purpose: 401 is not explicitly handled, should default to FATAL
        """
        print("\n=== Test: 401 Unauthorized → FATAL ===")
        
        # Act
        result = classify_error(status_code=401, reason=None)
        
        # Assert
        print(f"Classification result: {result}")
        assert result == ErrorType.FATAL, "401 should be FATAL (not explicitly RECOVERABLE)"
    
    def test_classify_error_with_reason_string(self):
        """
        Test classification with various reason strings.
        
        What it does: Verifies reason parameter handling
        Purpose: Ensure reason strings are properly evaluated
        """
        print("\n=== Test: Various reason strings ===")
        
        # Test CONTENT_LENGTH_EXCEEDS_THRESHOLD
        result1 = classify_error(400, "CONTENT_LENGTH_EXCEEDS_THRESHOLD")
        print(f"400 + CONTENT_LENGTH: {result1}")
        assert result1 == ErrorType.FATAL
        
        # Test other reason
        result2 = classify_error(400, "SOME_OTHER_REASON")
        print(f"400 + SOME_OTHER_REASON: {result2}")
        assert result2 == ErrorType.FATAL
        
        # Test empty string (treated as truthy)
        result3 = classify_error(400, "")
        print(f"400 + empty string: {result3}")
        assert result3 == ErrorType.FATAL


class TestClassifyErrorComprehensive:
    """
    Comprehensive tests covering all documented error scenarios.
    """
    
    def test_all_recoverable_codes(self):
        """
        Test all RECOVERABLE status codes in one test.
        
        What it does: Batch verification of all RECOVERABLE codes
        Purpose: Ensure complete coverage of account-specific errors
        """
        print("\n=== Test: All RECOVERABLE codes ===")
        
        recoverable_codes = [402, 403, 429]
        
        for code in recoverable_codes:
            result = classify_error(code, None)
            print(f"Status {code}: {result}")
            assert result == ErrorType.RECOVERABLE, f"{code} should be RECOVERABLE"
    
    def test_all_fatal_5xx_codes(self):
        """
        Test that all 5xx codes are FATAL.
        
        What it does: Batch verification of server error codes
        Purpose: Ensure all server errors are classified as FATAL
        """
        print("\n=== Test: All 5xx codes → FATAL ===")
        
        server_error_codes = [500, 501, 502, 503, 504, 505]
        
        for code in server_error_codes:
            result = classify_error(code, None)
            print(f"Status {code}: {result}")
            assert result == ErrorType.FATAL, f"{code} should be FATAL"
    
    def test_400_with_different_reasons(self):
        """
        Test 400 classification with various reason codes.
        
        What it does: Comprehensive 400 reason testing
        Purpose: Verify correct classification based on reason
        """
        print("\n=== Test: 400 with different reasons ===")
        
        # FATAL reasons
        fatal_reasons = [
            "CONTENT_LENGTH_EXCEEDS_THRESHOLD",
            None,
            "UNKNOWN",
            "VALIDATION_ERROR",
            ""
        ]
        
        for reason in fatal_reasons:
            result = classify_error(400, reason)
            print(f"400 + reason={reason}: {result}")
            assert result == ErrorType.FATAL, f"400 + {reason} should be FATAL"
