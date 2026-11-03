# -*- coding: utf-8 -*-

"""
Unit tests for truncation_state.py - In-memory cache for truncation recovery.

Tests cover:
- Tool truncation save/retrieve operations
- Content truncation save/retrieve operations
- One-time retrieval pattern
- Thread safety
- Cache statistics
"""

import threading
import time
from typing import List

import pytest

from kiro.truncation_state import (
    save_tool_truncation,
    get_tool_truncation,
    save_content_truncation,
    get_content_truncation,
    get_cache_stats,
    ToolTruncationInfo,
    ContentTruncationInfo,
    _tool_truncation_cache,
    _content_truncation_cache
)


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear cache before and after each test to ensure isolation."""
    print("\n[Setup] Clearing truncation cache...")
    _tool_truncation_cache.clear()
    _content_truncation_cache.clear()
    yield
    print("[Teardown] Clearing truncation cache...")
    _tool_truncation_cache.clear()
    _content_truncation_cache.clear()


class TestToolTruncation:
    """Test suite for tool truncation cache operations."""
    
    def test_save_and_retrieve_tool_truncation(self):
        """
        Test Case 1.1: Save and retrieve tool truncation
        
        What it does: Verify tool truncation info can be saved and retrieved by tool_call_id
        Goal: Ensure basic cache operations work correctly
        """
        print("\n=== Test: Save and retrieve tool truncation ===")
        
        # Arrange
        tool_call_id = "tooluse_abc123"
        tool_name = "write_to_file"
        truncation_info = {"size_bytes": 5000, "reason": "missing 2 closing braces"}
        
        print(f"Saving truncation for tool_call_id={tool_call_id}, tool={tool_name}")
        
        # Act
        save_tool_truncation(tool_call_id, tool_name, truncation_info)
        
        # Assert - First retrieval should succeed
        print("First retrieval (should succeed)...")
        info = get_tool_truncation(tool_call_id)
        print(f"Retrieved: {info}")
        
        assert info is not None, "First retrieval should return info"
        assert isinstance(info, ToolTruncationInfo), "Should return ToolTruncationInfo instance"
        assert info.tool_call_id == tool_call_id, f"Expected tool_call_id={tool_call_id}, got {info.tool_call_id}"
        assert info.tool_name == tool_name, f"Expected tool_name={tool_name}, got {info.tool_name}"
        assert info.truncation_info == truncation_info, "Truncation info should match"
        assert info.timestamp > 0, "Timestamp should be set"
        
        # Assert - Second retrieval should fail (one-time retrieval)
        print("Second retrieval (should fail - one-time retrieval)...")
        info2 = get_tool_truncation(tool_call_id)
        print(f"Retrieved: {info2}")
        
        assert info2 is None, "Second retrieval should return None (one-time retrieval)"
        
        print("✅ Test passed: One-time retrieval works correctly")
    
    def test_retrieve_nonexistent_tool_truncation(self):
        """
        Test Case: Retrieve non-existent tool truncation
        
        What it does: Verify graceful handling when cache entry doesn't exist
        Goal: Ensure no errors when retrieving non-existent entries
        """
        print("\n=== Test: Retrieve non-existent tool truncation ===")
        
        # Act
        print("Retrieving non-existent tool_call_id...")
        info = get_tool_truncation("nonexistent_id")
        print(f"Retrieved: {info}")
        
        # Assert
        assert info is None, "Should return None for non-existent entry"
        
        print("✅ Test passed: Graceful handling of non-existent entries")
    
    def test_multiple_tool_truncations(self):
        """
        Test Case: Multiple tool truncations in cache
        
        What it does: Verify multiple truncations can coexist and be retrieved independently
        Goal: Ensure cache handles multiple entries correctly
        """
        print("\n=== Test: Multiple tool truncations ===")
        
        # Arrange
        tools = [
            ("tooluse_1", "write_to_file", {"size_bytes": 5000, "reason": "test1"}),
            ("tooluse_2", "read_file", {"size_bytes": 3000, "reason": "test2"}),
            ("tooluse_3", "execute_command", {"size_bytes": 7000, "reason": "test3"})
        ]
        
        # Act - Save all
        print("Saving 3 tool truncations...")
        for tool_id, tool_name, info in tools:
            save_tool_truncation(tool_id, tool_name, info)
        
        # Assert - Check stats
        stats = get_cache_stats()
        print(f"Cache stats: {stats}")
        assert stats["tool_truncations"] == 3, "Should have 3 tool truncations"
        
        # Assert - Retrieve in different order
        print("Retrieving tool_2...")
        info2 = get_tool_truncation("tooluse_2")
        assert info2 is not None, "Should retrieve tool_2"
        assert info2.tool_name == "read_file", "Should get correct tool"
        
        print("Retrieving tool_1...")
        info1 = get_tool_truncation("tooluse_1")
        assert info1 is not None, "Should retrieve tool_1"
        assert info1.tool_name == "write_to_file", "Should get correct tool"
        
        print("Retrieving tool_3...")
        info3 = get_tool_truncation("tooluse_3")
        assert info3 is not None, "Should retrieve tool_3"
        assert info3.tool_name == "execute_command", "Should get correct tool"
        
        # Assert - Cache should be empty now
        stats = get_cache_stats()
        print(f"Cache stats after retrieval: {stats}")
        assert stats["tool_truncations"] == 0, "Cache should be empty after all retrievals"
        
        print("✅ Test passed: Multiple truncations handled independently")


class TestContentTruncation:
    """Test suite for content truncation cache operations."""
    
    def test_save_and_retrieve_content_truncation(self):
        """
        Test Case 1.2: Save and retrieve content truncation
        
        What it does: Verify content truncation info can be saved and retrieved by content hash
        Goal: Ensure content-based tracking works correctly
        """
        print("\n=== Test: Save and retrieve content truncation ===")
        
        # Arrange
        content = "This is truncated content that was cut off mid-sentence and never completed properly..."
        
        print(f"Saving truncation for content (length={len(content)})...")
        
        # Act
        content_hash = save_content_truncation(content)
        print(f"Generated hash: {content_hash}")
        
        # Assert - Hash format
        assert isinstance(content_hash, str), "Hash should be string"
        assert len(content_hash) == 16, f"Hash should be 16 chars, got {len(content_hash)}"
        
        # Assert - First retrieval should succeed
        print("First retrieval (should succeed)...")
        info = get_content_truncation(content)
        print(f"Retrieved: {info}")
        
        assert info is not None, "First retrieval should return info"
        assert isinstance(info, ContentTruncationInfo), "Should return ContentTruncationInfo instance"
        assert info.message_hash == content_hash, "Hash should match"
        assert len(info.content_preview) <= 200, "Preview should be max 200 chars"
        assert info.timestamp > 0, "Timestamp should be set"
        
        # Assert - Second retrieval should fail (one-time retrieval)
        print("Second retrieval (should fail - one-time retrieval)...")
        info2 = get_content_truncation(content)
        print(f"Retrieved: {info2}")
        
        assert info2 is None, "Second retrieval should return None (one-time retrieval)"
        
        print("✅ Test passed: Content truncation one-time retrieval works")
    
    def test_content_hash_stability(self):
        """
        Test Case 1.3: Content hash stability
        
        What it does: Verify same content produces same hash
        Goal: Ensure deterministic hashing for reliable tracking
        """
        print("\n=== Test: Content hash stability ===")
        
        # Arrange
        content1 = "A" * 1000  # Long content
        content2 = "A" * 1000  # Same content
        
        print(f"Saving same content twice (length={len(content1)})...")
        
        # Act
        hash1 = save_content_truncation(content1)
        # Retrieve to clear cache
        get_content_truncation(content1)
        
        hash2 = save_content_truncation(content2)
        
        print(f"Hash 1: {hash1}")
        print(f"Hash 2: {hash2}")
        
        # Assert
        assert hash1 == hash2, "Same content should produce same hash (deterministic)"
        
        print("✅ Test passed: Hash is deterministic")
    
    def test_content_hash_uses_first_500_chars(self):
        """
        Test Case 1.4: Content hash uses first 500 chars only
        
        What it does: Verify hash is based on first 500 chars, not entire content
        Goal: Ensure efficient hashing for large content
        """
        print("\n=== Test: Content hash uses first 500 chars ===")
        
        # Arrange
        content_long = "A" * 10000  # 10k chars
        content_same_prefix = "A" * 500 + "B" * 9500  # Same first 500 chars
        
        print(f"Content 1: {len(content_long)} chars (all A)")
        print(f"Content 2: {len(content_same_prefix)} chars (500 A + 9500 B)")
        
        # Act
        hash1 = save_content_truncation(content_long)
        # Retrieve to clear cache
        get_content_truncation(content_long)
        
        hash2 = save_content_truncation(content_same_prefix)
        
        print(f"Hash 1: {hash1}")
        print(f"Hash 2: {hash2}")
        
        # Assert
        assert hash1 == hash2, "Content with same first 500 chars should produce same hash"
        
        # Verify retrieval works with either content
        info = get_content_truncation(content_long)
        assert info is not None, "Should retrieve with original content"
        
        print("✅ Test passed: Hash based on first 500 chars only")


class TestThreadSafety:
    """Test suite for thread safety of cache operations."""
    
    def test_concurrent_tool_truncation_saves(self):
        """
        Test Case 1.5: Thread safety for tool truncations
        
        What it does: Verify cache operations are thread-safe
        Goal: Ensure no race conditions or data corruption
        """
        print("\n=== Test: Concurrent tool truncation saves ===")
        
        # Arrange
        num_threads = 10
        results: List[ToolTruncationInfo] = []
        errors: List[Exception] = []
        
        def save_and_retrieve(tool_id: str):
            try:
                print(f"Thread {tool_id}: Saving...")
                save_tool_truncation(tool_id, f"tool_{tool_id}", {"test": tool_id})
                time.sleep(0.001)  # Small delay to increase chance of race conditions
                print(f"Thread {tool_id}: Retrieving...")
                info = get_tool_truncation(tool_id)
                if info:
                    results.append(info)
            except Exception as e:
                errors.append(e)
        
        # Act
        print(f"Starting {num_threads} threads...")
        threads = []
        for i in range(num_threads):
            thread = threading.Thread(target=save_and_retrieve, args=(f"tool_{i}",))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        print(f"All threads completed. Results: {len(results)}, Errors: {len(errors)}")
        
        # Assert
        assert len(errors) == 0, f"Should have no errors, got: {errors}"
        assert len(results) == num_threads, f"Should retrieve all {num_threads} entries"
        
        # Verify no cross-contamination
        tool_ids = [info.tool_call_id for info in results]
        assert len(set(tool_ids)) == num_threads, "All tool_ids should be unique (no cross-contamination)"
        
        print("✅ Test passed: Thread-safe operations")
    
    def test_concurrent_content_truncation_saves(self):
        """
        Test Case: Thread safety for content truncations
        
        What it does: Verify content cache operations are thread-safe
        Goal: Ensure no race conditions with content hashing
        """
        print("\n=== Test: Concurrent content truncation saves ===")
        
        # Arrange
        num_threads = 10
        results: List[ContentTruncationInfo] = []
        errors: List[Exception] = []
        
        def save_and_retrieve(content: str):
            try:
                print(f"Thread {content[:10]}: Saving...")
                save_content_truncation(content)
                time.sleep(0.001)
                print(f"Thread {content[:10]}: Retrieving...")
                info = get_content_truncation(content)
                if info:
                    results.append(info)
            except Exception as e:
                errors.append(e)
        
        # Act
        print(f"Starting {num_threads} threads...")
        threads = []
        for i in range(num_threads):
            content = f"Content_{i}_" + "X" * 100
            thread = threading.Thread(target=save_and_retrieve, args=(content,))
            threads.append(thread)
            thread.start()
        
        # Wait for all threads
        for thread in threads:
            thread.join()
        
        print(f"All threads completed. Results: {len(results)}, Errors: {len(errors)}")
        
        # Assert
        assert len(errors) == 0, f"Should have no errors, got: {errors}"
        assert len(results) == num_threads, f"Should retrieve all {num_threads} entries"
        
        print("✅ Test passed: Thread-safe content operations")


class TestCacheStats:
    """Test suite for cache statistics."""
    
    def test_cache_stats_empty(self):
        """
        Test Case: Cache stats when empty
        
        What it does: Verify stats return zeros for empty cache
        Goal: Ensure stats work correctly in edge case
        """
        print("\n=== Test: Cache stats (empty) ===")
        
        # Act
        stats = get_cache_stats()
        print(f"Stats: {stats}")
        
        # Assert
        assert stats["tool_truncations"] == 0, "Should have 0 tool truncations"
        assert stats["content_truncations"] == 0, "Should have 0 content truncations"
        assert stats["total"] == 0, "Total should be 0"
        
        print("✅ Test passed: Empty cache stats")
    
    def test_cache_stats_with_entries(self):
        """
        Test Case 1.6: Cache stats with entries
        
        What it does: Verify get_cache_stats() returns correct counts
        Goal: Ensure monitoring functionality works
        """
        print("\n=== Test: Cache stats with entries ===")
        
        # Arrange
        print("Adding 2 tool truncations and 1 content truncation...")
        save_tool_truncation("id1", "tool1", {})
        save_tool_truncation("id2", "tool2", {})
        save_content_truncation("content1")
        
        # Act
        stats = get_cache_stats()
        print(f"Stats: {stats}")
        
        # Assert
        assert stats["tool_truncations"] == 2, "Should have 2 tool truncations"
        assert stats["content_truncations"] == 1, "Should have 1 content truncation"
        assert stats["total"] == 3, "Total should be 3"
        
        # Act - Retrieve one entry
        print("Retrieving one tool truncation...")
        get_tool_truncation("id1")
        
        stats = get_cache_stats()
        print(f"Stats after retrieval: {stats}")
        
        # Assert
        assert stats["tool_truncations"] == 1, "Should have 1 tool truncation left"
        assert stats["total"] == 2, "Total should be 2"
        
        print("✅ Test passed: Cache stats accurate")


class TestHasPending:
    """Tests for has_pending() fast-path check."""

    def test_false_when_both_caches_empty(self):
        """
        What it does: Checks has_pending with empty caches.
        Purpose: Routes skip the recovery scan in the common case.
        """
        from kiro.truncation_state import has_pending
        assert has_pending() is False

    def test_true_with_tool_entry_only(self):
        """
        What it does: Saves only a tool truncation.
        Purpose: Either cache being non-empty triggers the scan.
        """
        from kiro.truncation_state import has_pending
        save_tool_truncation("call_1", "Write", {"reason": "x"})
        assert has_pending() is True

    def test_true_with_content_entry_only(self):
        """
        What it does: Saves only a content truncation.
        Purpose: Either cache being non-empty triggers the scan.
        """
        from kiro.truncation_state import has_pending
        save_content_truncation("truncated text")
        assert has_pending() is True

    def test_false_again_after_entries_consumed(self):
        """
        What it does: Saves and then retrieves (one-time) both kinds.
        Purpose: has_pending reflects consumption, so the fast path resumes.
        """
        from kiro.truncation_state import has_pending
        save_tool_truncation("call_2", "Write", {})
        save_content_truncation("abc")
        assert has_pending() is True
        assert get_tool_truncation("call_2") is not None
        assert has_pending() is True
        assert get_content_truncation("abc") is not None
        assert has_pending() is False

    def test_returns_bool(self):
        """
        What it does: Checks the return type in both states.
        Purpose: Callers may compare with `is`.
        """
        from kiro.truncation_state import has_pending
        assert isinstance(has_pending(), bool)
        save_tool_truncation("call_3", "t", {})
        assert isinstance(has_pending(), bool)
