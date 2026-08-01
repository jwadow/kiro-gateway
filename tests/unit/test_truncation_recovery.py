# -*- coding: utf-8 -*-

"""
Unit tests for truncation_recovery.py - Synthetic message generation.

Tests cover:
- Tool truncation message generation
- Content truncation message generation
- Recovery enabled/disabled check
- Message format validation
"""

import os
from unittest.mock import patch

import pytest

from kiro.truncation_recovery import (
    should_inject_recovery,
    generate_truncation_tool_result,
    generate_tool_protocol_failure_message,
    generate_truncation_user_message
)


class TestRecoveryEnabledCheck:
    """Test suite for recovery enabled/disabled check."""
    
    def test_should_inject_recovery_when_enabled(self):
        """
        Test Case 2.3: Recovery enabled check (enabled)
        
        What it does: Verify should_inject_recovery() returns True when enabled
        Goal: Ensure config is respected
        """
        print("\n=== Test: Recovery enabled check (enabled) ===")
        
        # Arrange & Act
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "true"}):
            # Need to reload config to pick up env change
            from importlib import reload
            from kiro import config
            reload(config)
            
            result = should_inject_recovery()
            print(f"TRUNCATION_RECOVERY=true → should_inject_recovery() = {result}")
        
        # Assert
        assert result is True, "Should return True when TRUNCATION_RECOVERY=true"
        
        print("✅ Test passed: Recovery enabled check works")
    
    def test_should_inject_recovery_when_disabled(self):
        """
        Test Case 2.3: Recovery enabled check (disabled)
        
        What it does: Verify should_inject_recovery() returns False when disabled
        Goal: Ensure config is respected
        """
        print("\n=== Test: Recovery enabled check (disabled) ===")
        
        # Arrange & Act
        with patch.dict(os.environ, {"TRUNCATION_RECOVERY": "false"}):
            # Need to reload config to pick up env change
            from importlib import reload
            from kiro import config
            reload(config)
            
            result = should_inject_recovery()
            print(f"TRUNCATION_RECOVERY=false → should_inject_recovery() = {result}")
        
        # Assert
        assert result is False, "Should return False when TRUNCATION_RECOVERY=false"
        
        print("✅ Test passed: Recovery disabled check works")


class TestToolTruncationMessage:
    """Test suite for tool truncation message generation."""
    
    def test_generate_truncation_tool_result_format(self):
        """
        Test Case 2.1: Generate tool truncation message
        
        What it does: Verify synthetic tool_result message format
        Goal: Ensure message structure is correct for both APIs
        """
        print("\n=== Test: Generate tool truncation message ===")
        
        # Arrange
        tool_name = "write_to_file"
        tool_use_id = "tooluse_xyz123"
        truncation_info = {"size_bytes": 5000, "reason": "missing 1 closing brace"}
        
        print(f"Generating message for tool={tool_name}, id={tool_use_id}")
        
        # Act
        result = generate_truncation_tool_result(tool_name, tool_use_id, truncation_info)
        print(f"Generated result: {result}")
        
        # Assert - Structure
        assert isinstance(result, dict), "Should return dict"
        assert result["type"] == "tool_result", "Type should be 'tool_result'"
        assert result["tool_use_id"] == tool_use_id, f"tool_use_id should be {tool_use_id}"
        assert result["is_error"] is True, "is_error should be True"
        
        # Assert - Content
        content = result["content"]
        assert isinstance(content, str), "Content should be string"
        assert len(content) > 0, "Content should not be empty"
        
        # Large truncations are size pressure and require splitting the operation.
        assert "[API Limitation]" in content
        assert "truncated" in content.lower()
        assert "upstream api" in content.lower()
        assert "due to its size" in content.lower()
        assert "repeating" in content.lower()
        assert "split" in content.lower() or "smaller" in content.lower()
        
        print("✅ Test passed: Tool truncation message format correct")
    
    def test_generate_truncation_tool_result_different_tools(self):
        """
        Test Case: Generate messages for different tools
        
        What it does: Verify message generation works for various tool names
        Goal: Ensure no tool-specific hardcoding
        """
        print("\n=== Test: Generate messages for different tools ===")
        
        # Arrange
        tools = [
            ("write_to_file", "tooluse_1"),
            ("read_file", "tooluse_2"),
            ("execute_command", "tooluse_3"),
            ("search_files", "tooluse_4")
        ]
        
        # Act & Assert
        for tool_name, tool_id in tools:
            print(f"Testing tool: {tool_name}")
            result = generate_truncation_tool_result(
                tool_name=tool_name,
                tool_use_id=tool_id,
                truncation_info={"size_bytes": 1000, "reason": "test"}
            )
            
            assert result["type"] == "tool_result", f"Should work for {tool_name}"
            assert result["tool_use_id"] == tool_id, f"Should preserve tool_id for {tool_name}"
            assert "[Upstream Glitch]" in result["content"], f"Should mark small cutoff for {tool_name}"
            assert "retry" in result["content"].lower()
        
        print("✅ Test passed: Works for all tool types")
    
    def test_generate_truncation_tool_result_no_specific_instructions(self):
        """
        Test Case: Message doesn't give specific instructions
        
        What it does: Verify message doesn't tell model HOW to fix (e.g., "break into steps")
        Goal: Ensure universal formulation without micro-management
        """
        print("\n=== Test: Message doesn't give specific instructions ===")
        
        # Arrange
        result = generate_truncation_tool_result(
            tool_name="write_to_file",
            tool_use_id="test",
            truncation_info={"size_bytes": 5000, "reason": "test"}
        )
        
        content = result["content"].lower()
        print(f"Checking content for specific instructions...")
        
        # Assert - Should NOT contain specific instructions
        forbidden_phrases = [
            "break into smaller",
            "split the file",
            "write in chunks",
            "reduce the size",
            "make it shorter",
            "use multiple calls"
        ]
        
        for phrase in forbidden_phrases:
            assert phrase not in content, f"Should NOT contain specific instruction: '{phrase}'"
        
        # Large write-like failures should recommend splitting without leaking data.
        assert "split" in content or "smaller" in content
        assert "repeating" in content
        
        print("✅ Test passed: No specific instructions (universal formulation)")


class TestToolProtocolFailureMessage:
    def test_malformed_message_is_redacted_and_non_executable(self):
        raw_arguments = '{"secret": "sensitive", nope}'
        tool_call = {
            "id": "call_bad",
            "function": {"name": "Write", "arguments": raw_arguments},
            "_protocol_failure": {
                "classification": "malformed",
                "reason": "malformed JSON",
                "size_bytes": len(raw_arguments),
            },
            "_executable": False,
        }

        message = generate_tool_protocol_failure_message(tool_call)

        assert "[Tool Protocol Error]" in message
        assert "No tool was executed" in message
        assert "valid JSON" in message
        assert raw_arguments not in message
        assert "sensitive" not in message

    def test_truncated_message_preserves_retry_guidance(self):
        tool_call = {
            "id": "call_cut",
            "function": {"name": "Agent", "arguments": '{"prompt": "cut'},
            "_protocol_failure": {
                "classification": "truncated",
                "reason": "unclosed string literal",
                "size_bytes": 15,
            },
            "_executable": False,
        }

        message = generate_tool_protocol_failure_message(tool_call)

        assert "[Upstream Glitch]" in message
        assert "retry" in message.lower()
        assert "No tool was executed" in message


class TestContentTruncationMessage:
    """Test suite for content truncation message generation."""
    
    def test_generate_truncation_user_message_format(self):
        """
        Test Case 2.2: Generate content truncation message
        
        What it does: Verify synthetic user message format
        Goal: Ensure message is appropriate for content truncation
        """
        print("\n=== Test: Generate content truncation message ===")
        
        # Act
        message = generate_truncation_user_message()
        print(f"Generated message: {message}")
        
        # Assert - Basic structure
        assert isinstance(message, str), "Should return string"
        assert len(message) > 0, "Should not be empty"
        
        # Assert - Key markers
        assert "[System Notice]" in message, "Should contain [System Notice] marker"
        
        # Assert - Key phrases
        assert "truncated" in message.lower(), "Should mention truncation"
        assert "api" in message.lower(), "Should mention API"
        assert "output size" in message.lower() or "size limit" in message.lower(), "Should mention size limits"
        
        # Assert - Not model's fault
        assert "not an error on your part" in message.lower() or "not your fault" in message.lower(), \
            "Should clarify it's not model's fault"
        
        # Assert - Adaptation suggestion
        assert "adapt" in message.lower(), "Should suggest adaptation"
        
        print("✅ Test passed: Content truncation message format correct")
    
    def test_generate_truncation_user_message_no_micro_steps(self):
        """
        Test Case: Message doesn't cause micro-steps
        
        What it does: Verify message doesn't tell model to "break into steps"
        Goal: Prevent micro-step behavior that was problematic in earlier iterations
        """
        print("\n=== Test: Message doesn't cause micro-steps ===")
        
        # Act
        message = generate_truncation_user_message()
        content = message.lower()
        print(f"Checking for micro-step triggers...")
        
        # Assert - Should NOT contain phrases that cause micro-steps
        forbidden_phrases = [
            "break into steps",
            "step by step",
            "one step at a time",
            "smaller steps",
            "incremental"
        ]
        
        for phrase in forbidden_phrases:
            assert phrase not in content, f"Should NOT contain micro-step trigger: '{phrase}'"
        
        print("✅ Test passed: No micro-step triggers")
    
    def test_generate_truncation_user_message_consistency(self):
        """
        Test Case: Message is consistent across calls
        
        What it does: Verify same message is generated each time
        Goal: Ensure deterministic behavior
        """
        print("\n=== Test: Message consistency ===")
        
        # Act
        message1 = generate_truncation_user_message()
        message2 = generate_truncation_user_message()
        message3 = generate_truncation_user_message()
        
        print(f"Message 1: {message1[:50]}...")
        print(f"Message 2: {message2[:50]}...")
        print(f"Message 3: {message3[:50]}...")
        
        # Assert
        assert message1 == message2 == message3, "Should generate same message each time (deterministic)"
        
        print("✅ Test passed: Message is consistent")


class TestMessageIntegration:
    """Test suite for message integration scenarios."""
    
    def test_tool_result_can_be_prepended_to_original(self):
        """
        Test Case: Tool result can be prepended to original content
        
        What it does: Verify synthetic message can be combined with original tool_result
        Goal: Ensure message format works with prepending pattern
        """
        print("\n=== Test: Tool result prepending ===")
        
        # Arrange
        synthetic = generate_truncation_tool_result(
            tool_name="write_to_file",
            tool_use_id="test",
            truncation_info={"size_bytes": 5000, "reason": "test"}
        )
        original_content = "Error: Missing required parameter 'content'"
        
        # Act - Simulate prepending (as done in routes)
        combined = f"{synthetic['content']}\n\n---\n\nOriginal tool result:\n{original_content}"
        
        print(f"Combined length: {len(combined)} chars")
        print(f"Combined preview: {combined[:100]}...")
        
        # Assert
        assert "[API Limitation]" in combined, "Should contain synthetic message"
        assert original_content in combined, "Should contain original content"
        assert combined.index("[API Limitation]") < combined.index(original_content), \
            "Synthetic message should come before original"
        
        print("✅ Test passed: Prepending works correctly")
    
    def test_user_message_can_be_inserted_after_assistant(self):
        """
        Test Case: User message can be inserted after assistant message
        
        What it does: Verify synthetic user message works in conversation flow
        Goal: Ensure message format works with insertion pattern
        """
        print("\n=== Test: User message insertion ===")
        
        # Arrange
        assistant_message = "Here's the code you requested:\n\n```python\n# This is a very long file..."
        synthetic_user_message = generate_truncation_user_message()
        
        # Act - Simulate conversation flow
        conversation = [
            {"role": "user", "content": "Write a large file"},
            {"role": "assistant", "content": assistant_message},
            {"role": "user", "content": synthetic_user_message}  # Inserted
        ]
        
        print(f"Conversation has {len(conversation)} messages")
        print(f"Last message: {conversation[-1]['content'][:50]}...")
        
        # Assert
        assert len(conversation) == 3, "Should have 3 messages"
        assert conversation[-1]["role"] == "user", "Last message should be user"
        assert "[System Notice]" in conversation[-1]["content"], "Should contain system notice"
        
        print("✅ Test passed: Insertion works correctly")
