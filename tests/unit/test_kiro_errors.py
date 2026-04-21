# -*- coding: utf-8 -*-

"""
Unit tests for Kiro API error enhancement system.
Tests enhance_kiro_error() function and KiroErrorInfo dataclass.
"""

import pytest

from kiro.kiro_errors import (
    KiroErrorInfo,
    enhance_kiro_error
)


class TestEnhanceKiroErrorContentLength:
    """Tests for CONTENT_LENGTH_EXCEEDS_THRESHOLD error enhancement."""
    
    def test_content_length_error_enhanced_successfully(self):
        """
        What it does: Verifies CONTENT_LENGTH_EXCEEDS_THRESHOLD is enhanced with user-friendly message.
        Purpose: Ensure cryptic Amazon error is replaced with clear, actionable message (issue #63).
        """
        print("Setup: Creating error JSON with CONTENT_LENGTH_EXCEEDS_THRESHOLD...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: User message is enhanced...")
        print(f"Comparing user_message: Expected 'Model context limit reached...', Got '{error_info.user_message}'")
        assert error_info.user_message == "Model context limit reached. Conversation size exceeds model capacity."
        assert error_info.reason == "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        assert error_info.original_message == "Input is too long."
    
    def test_content_length_error_preserves_original_message(self):
        """
        What it does: Verifies original message is preserved for logging.
        Purpose: Ensure debugging information is not lost during enhancement.
        """
        print("Setup: Creating error JSON...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Original message preserved...")
        assert error_info.original_message == "Input is too long."
        assert error_info.original_message != error_info.user_message
    
    def test_content_length_error_reason_string_correct(self):
        """
        What it does: Verifies reason is correctly preserved as string.
        Purpose: Ensure reason field can be used for programmatic error handling.
        """
        print("Setup: Creating error JSON...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Reason is correct string value...")
        assert error_info.reason == "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        assert isinstance(error_info.reason, str)
    
    def test_content_length_error_no_reason_suffix(self):
        """
        What it does: Verifies enhanced message doesn't include (reason: ...) suffix.
        Purpose: Ensure clean, user-friendly message without technical codes.
        """
        print("Setup: Creating error JSON...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: No (reason: ...) in user message...")
        assert "(reason:" not in error_info.user_message
        assert "CONTENT_LENGTH_EXCEEDS_THRESHOLD" not in error_info.user_message


class TestEnhanceKiroErrorMonthlyLimit:
    """Tests for MONTHLY_REQUEST_COUNT error enhancement."""
    
    def test_monthly_limit_error_enhanced_successfully(self):
        """
        What it does: Verifies MONTHLY_REQUEST_COUNT is enhanced with user-friendly message.
        Purpose: Ensure monthly quota error is clear and actionable.
        """
        print("Setup: Creating error JSON with MONTHLY_REQUEST_COUNT...")
        error_json = {
            "message": "You have reached the limit.",
            "reason": "MONTHLY_REQUEST_COUNT"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: User message is enhanced...")
        assert error_info.user_message == "Monthly request limit exceeded. Account has reached its monthly quota."
        assert error_info.reason == "MONTHLY_REQUEST_COUNT"
        assert error_info.original_message == "You have reached the limit."
    
    def test_monthly_limit_error_no_reason_suffix(self):
        """
        What it does: Verifies enhanced message doesn't include (reason: ...) suffix.
        Purpose: Ensure clean, user-friendly message without technical codes.
        """
        print("Setup: Creating error JSON...")
        error_json = {
            "message": "You have reached the limit.",
            "reason": "MONTHLY_REQUEST_COUNT"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: No (reason: ...) in user message...")
        assert "(reason:" not in error_info.user_message
        assert "MONTHLY_REQUEST_COUNT" not in error_info.user_message


class TestEnhanceKiroErrorUnknown:
    """Tests for unknown error handling."""
    
    def test_unknown_reason_keeps_original_with_suffix(self):
        """
        What it does: Verifies unknown reasons keep original message with (reason: ...) suffix.
        Purpose: Ensure unrecognized errors are passed through with context.
        """
        print("Setup: Creating error JSON with unknown reason...")
        error_json = {
            "message": "Something went wrong.",
            "reason": "UNKNOWN_FUTURE_ERROR"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Original message with reason suffix...")
        print(f"User message: {error_info.user_message}")
        assert error_info.user_message == "Something went wrong. (reason: UNKNOWN_FUTURE_ERROR)"
        assert error_info.reason == "UNKNOWN_FUTURE_ERROR"
        assert error_info.original_message == "Something went wrong."
    
    def test_unknown_reason_preserved_as_string(self):
        """
        What it does: Verifies unknown reasons are preserved as-is (not mapped to "UNKNOWN").
        Purpose: Ensure graceful handling of future Amazon error codes without information loss.
        """
        print("Setup: Creating error JSON with unknown reason...")
        error_json = {
            "message": "Error occurred.",
            "reason": "RATE_LIMIT_EXCEEDED"  # Future error not yet enhanced
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Reason preserved as original string...")
        assert error_info.reason == "RATE_LIMIT_EXCEEDED"
        assert error_info.user_message == "Error occurred. (reason: RATE_LIMIT_EXCEEDED)"
    
    def test_missing_reason_field_uses_unknown(self):
        """
        What it does: Verifies missing reason field defaults to UNKNOWN.
        Purpose: Ensure graceful handling of errors without reason field.
        """
        print("Setup: Creating error JSON without reason field...")
        error_json = {
            "message": "An error occurred."
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Reason is UNKNOWN, no suffix in message...")
        assert error_info.reason == "UNKNOWN"
        assert error_info.user_message == "An error occurred."
        assert "(reason:" not in error_info.user_message
    
    def test_reason_unknown_string_no_suffix(self):
        """
        What it does: Verifies reason="UNKNOWN" doesn't add redundant suffix.
        Purpose: Ensure clean message when reason is explicitly UNKNOWN.
        """
        print("Setup: Creating error JSON with reason='UNKNOWN'...")
        error_json = {
            "message": "Unknown error.",
            "reason": "UNKNOWN"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: No redundant (reason: UNKNOWN) suffix...")
        assert error_info.user_message == "Unknown error."
        assert "(reason: UNKNOWN)" not in error_info.user_message


class TestEnhanceKiroErrorEdgeCases:
    """Tests for edge cases and malformed input."""
    
    def test_empty_error_json_uses_defaults(self):
        """
        What it does: Verifies empty error JSON uses default values.
        Purpose: Ensure graceful handling of malformed API responses.
        """
        print("Setup: Creating empty error JSON...")
        error_json = {}
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Default values used...")
        assert error_info.original_message == "Unknown error"
        assert error_info.reason == "UNKNOWN"
        assert error_info.user_message == "Unknown error"
    
    def test_missing_message_field_uses_default(self):
        """
        What it does: Verifies missing message field uses "Unknown error" default.
        Purpose: Ensure graceful handling when message field is absent.
        """
        print("Setup: Creating error JSON without message field...")
        error_json = {
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Default message used, but enhancement still applied...")
        assert error_info.original_message == "Unknown error"
        # Enhancement should still work based on reason
        assert error_info.user_message == "Model context limit reached. Conversation size exceeds model capacity."
    
    def test_empty_message_string_preserved(self):
        """
        What it does: Verifies empty message string is preserved (not replaced with default).
        Purpose: Ensure explicit empty strings are distinguished from missing fields.
        """
        print("Setup: Creating error JSON with empty message...")
        error_json = {
            "message": "",
            "reason": "SOME_ERROR"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Empty string preserved...")
        assert error_info.original_message == ""
        assert error_info.user_message == " (reason: SOME_ERROR)"
    
    def test_none_values_handled_gracefully(self):
        """
        What it does: Verifies None values in error JSON are handled gracefully.
        Purpose: Ensure robustness against unexpected None values.
        """
        print("Setup: Creating error JSON with None values...")
        error_json = {
            "message": None,
            "reason": None
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Defaults used for None values...")
        assert error_info.original_message == "Unknown error"
        assert error_info.reason == "UNKNOWN"
    
    def test_extra_fields_ignored(self):
        """
        What it does: Verifies extra fields in error JSON are ignored.
        Purpose: Ensure forward compatibility with future API changes.
        """
        print("Setup: Creating error JSON with extra fields...")
        error_json = {
            "message": "Error occurred.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD",
            "extra_field": "extra_value",
            "another_field": 123
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Extra fields don't affect enhancement...")
        assert error_info.user_message == "Model context limit reached. Conversation size exceeds model capacity."
        assert error_info.reason == "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
    
    def test_case_sensitive_reason_matching(self):
        """
        What it does: Verifies reason matching is case-sensitive.
        Purpose: Ensure exact string matching (Amazon API uses uppercase).
        """
        print("Setup: Creating error JSON with lowercase reason...")
        error_json = {
            "message": "Error.",
            "reason": "content_length_exceeds_threshold"  # lowercase
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Lowercase reason not matched, passed through as-is...")
        assert error_info.reason == "content_length_exceeds_threshold"
        assert error_info.user_message == "Error. (reason: content_length_exceeds_threshold)"


class TestEnhanceKiroErrorMessageQuality:
    """Tests for message quality and user experience."""
    
    def test_enhanced_message_is_user_friendly(self):
        """
        What it does: Verifies enhanced message is clear and non-technical.
        Purpose: Ensure end users can understand the error without technical knowledge.
        """
        print("Setup: Creating CONTENT_LENGTH_EXCEEDS_THRESHOLD error...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Message is user-friendly...")
        message = error_info.user_message
        # Should mention "context limit" (technical but understandable)
        assert "context limit" in message.lower()
        # Should mention "conversation" (user-facing term)
        assert "conversation" in message.lower()
        # Should NOT contain technical jargon
        assert "threshold" not in message.lower()
        assert "input" not in message.lower()
    
    def test_enhanced_message_indicates_model_limitation(self):
        """
        What it does: Verifies message indicates it's a model limitation, not gateway error.
        Purpose: Ensure users understand the error is from the model, not our service.
        """
        print("Setup: Creating CONTENT_LENGTH_EXCEEDS_THRESHOLD error...")
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Message indicates model limitation...")
        message = error_info.user_message
        assert "model" in message.lower()
        assert "limit" in message.lower()
    
    def test_unknown_error_preserves_original_context(self):
        """
        What it does: Verifies unknown errors preserve original message for context.
        Purpose: Ensure users get Amazon's original error when we can't enhance it.
        """
        print("Setup: Creating unknown error...")
        error_json = {
            "message": "Service temporarily unavailable.",
            "reason": "SERVICE_UNAVAILABLE"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Original message preserved with reason...")
        assert "Service temporarily unavailable" in error_info.user_message
        assert "SERVICE_UNAVAILABLE" in error_info.user_message


class TestKiroErrorInfoDataclass:
    """Tests for KiroErrorInfo dataclass."""
    
    def test_kiro_error_info_creation(self):
        """
        What it does: Verifies KiroErrorInfo can be created with all fields.
        Purpose: Ensure dataclass structure is correct.
        """
        print("Setup: Creating KiroErrorInfo...")
        error_info = KiroErrorInfo(
            reason="CONTENT_LENGTH_EXCEEDS_THRESHOLD",
            user_message="Test message",
            original_message="Original message"
        )
        
        print("Verification: All fields accessible...")
        assert error_info.reason == "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        assert error_info.user_message == "Test message"
        assert error_info.original_message == "Original message"
    
    def test_kiro_error_info_fields_accessible(self):
        """
        What it does: Verifies KiroErrorInfo fields can be accessed.
        Purpose: Ensure error info structure is usable.
        """
        print("Setup: Creating KiroErrorInfo...")
        error_info = KiroErrorInfo(
            reason="UNKNOWN",
            user_message="Message",
            original_message="Original"
        )
        
        print("Verification: Fields are accessible...")
        assert hasattr(error_info, 'reason')
        assert hasattr(error_info, 'user_message')
        assert hasattr(error_info, 'original_message')


class TestEnhanceKiroErrorIntegration:
    """Integration tests for real-world scenarios."""
    
    def test_real_world_content_length_error(self):
        """
        What it does: Verifies enhancement works with real Kiro API error format.
        Purpose: Ensure compatibility with actual Amazon API responses (issue #63).
        """
        print("Setup: Creating real-world error JSON from Kiro API...")
        # This is the actual format from issue #63
        error_json = {
            "message": "Input is too long.",
            "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
        }
        
        print("Action: Enhancing error...")
        error_info = enhance_kiro_error(error_json)
        
        print("Verification: Real-world error enhanced correctly...")
        assert "Model context limit reached" in error_info.user_message
        assert "Conversation size exceeds model capacity" in error_info.user_message
        assert error_info.reason == "CONTENT_LENGTH_EXCEEDS_THRESHOLD"
    
    def test_multiple_errors_enhanced_independently(self):
        """
        What it does: Verifies multiple errors can be enhanced independently.
        Purpose: Ensure stateless enhancement (no side effects between calls).
        """
        print("Setup: Creating multiple error JSONs...")
        error1 = {"message": "Error 1", "reason": "CONTENT_LENGTH_EXCEEDS_THRESHOLD"}
        error2 = {"message": "Error 2", "reason": "UNKNOWN_ERROR"}
        error3 = {"message": "Error 3"}
        
        print("Action: Enhancing all errors...")
        info1 = enhance_kiro_error(error1)
        info2 = enhance_kiro_error(error2)
        info3 = enhance_kiro_error(error3)
        
        print("Verification: Each error enhanced independently...")
        assert info1.user_message == "Model context limit reached. Conversation size exceeds model capacity."
        assert info2.user_message == "Error 2 (reason: UNKNOWN_ERROR)"
        assert info3.user_message == "Error 3"
        # Verify no cross-contamination
        assert info1.original_message == "Error 1"
        assert info2.original_message == "Error 2"
        assert info3.original_message == "Error 3"


class TestEnhanceImproperlyFormedRequest:
    """Tests for 'Improperly formed request.' error enhancement (issue #73)."""

    def test_enhance_improperly_formed_request_null_reason(self):
        """
        'Improperly formed request.' with null/UNKNOWN reason is enhanced
        to a clear payload-size message.
        """
        error_json = {
            "message": "Improperly formed request.",
            "reason": None,
        }
        error_info = enhance_kiro_error(error_json)

        assert "payload size exceeded" in error_info.user_message
        assert "/compact" in error_info.user_message
        assert error_info.original_message == "Improperly formed request."

    def test_enhance_improperly_formed_request_unknown_reason(self):
        """Same enhancement when reason field is missing (defaults to UNKNOWN)."""
        error_json = {"message": "Improperly formed request."}
        error_info = enhance_kiro_error(error_json)

        assert "payload size exceeded" in error_info.user_message

    def test_improperly_formed_with_real_reason_not_enhanced(self):
        """If reason is a real code, don't apply the size-limit enhancement."""
        error_json = {
            "message": "Improperly formed request.",
            "reason": "VALIDATION_ERROR",
        }
        error_info = enhance_kiro_error(error_json)

        # Should fall through to generic handler, not the size-limit message
        assert "payload size exceeded" not in error_info.user_message
