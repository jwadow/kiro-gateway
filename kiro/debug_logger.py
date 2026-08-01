# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

"""
Debug logging module for requests.

Supports three modes (DEBUG_MODE):
- off: logging disabled
- errors: logs are saved only on errors (4xx, 5xx)
- all: logs are overwritten on each request

In "errors" mode, data is buffered in memory and flushed to files
only when flush_on_error() is called.

Also captures application logs (loguru) for each request and saves
them to app_logs.txt file for debugging convenience.
"""

import io
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from loguru import logger

from kiro.config import DEBUG_MODE, DEBUG_DIR


class DebugLogger:
    """
    Singleton for managing debug request logs.
    
    Operating modes:
    - off: does nothing
    - errors: buffers data, flushes to files only on errors
    - all: writes data immediately to files (as before)
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DebugLogger, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self.debug_dir = Path(DEBUG_DIR)
        self._initialized = True
        
        # Buffers for "errors" mode
        self._request_body_buffer: Optional[bytes] = None
        self._kiro_request_body_buffer: Optional[bytes] = None
        self._raw_chunks_buffer: bytearray = bytearray()
        self._modified_chunks_buffer: bytearray = bytearray()
        
        # Buffer for application logs (loguru)
        self._app_logs_buffer: io.StringIO = io.StringIO()
        self._loguru_sink_id: Optional[int] = None

        # Accumulated protocol anomalies for the current request. Persisted
        # immediately (metadata-only) and independently of the error-flush
        # lifecycle, since anomalies can occur on otherwise-successful responses.
        self._anomaly_buffer: list = []
    
    def _is_enabled(self) -> bool:
        """Checks if logging is enabled."""
        return DEBUG_MODE in ("errors", "all")
    
    def _is_immediate_write(self) -> bool:
        """Checks if immediate file writing is needed (all mode)."""
        return DEBUG_MODE == "all"
    
    def _clear_buffers(self):
        """Clears all buffers."""
        self._request_body_buffer = None
        self._kiro_request_body_buffer = None
        self._raw_chunks_buffer.clear()
        self._modified_chunks_buffer.clear()
        self._anomaly_buffer = []
        self._clear_app_logs_buffer()
    
    def _clear_app_logs_buffer(self):
        """Clears the application logs buffer and removes sink."""
        # Remove sink from loguru
        if self._loguru_sink_id is not None:
            try:
                logger.remove(self._loguru_sink_id)
            except ValueError:
                # Sink already removed
                pass
            self._loguru_sink_id = None
        
        # Clear buffer
        self._app_logs_buffer = io.StringIO()
    
    def _setup_app_logs_capture(self):
        """
        Sets up application log capture to buffer.
        
        Adds a temporary sink to loguru that writes to StringIO buffer.
        Captures ALL logs without filtering, as sink is active only
        during processing of a specific request.
        """
        # Remove previous sink if exists
        self._clear_app_logs_buffer()
        
        # Add new sink to capture ALL logs
        # Format: time | level | module:function:line | message
        self._loguru_sink_id = logger.add(
            self._app_logs_buffer,
            format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
            level="DEBUG",  # Capture all levels from DEBUG and above
            colorize=False,  # No ANSI colors in file
            # No filter - capture ALL logs during request processing
        )

    def prepare_new_request(self):
        """
        Prepares the logger for a new request.
        
        In "all" mode: clears the logs folder.
        In "errors" mode: clears buffers.
        In both modes: sets up application log capture.
        """
        if not self._is_enabled():
            return
        
        # Clear buffers in any case
        self._clear_buffers()
        
        # Set up application log capture
        self._setup_app_logs_capture()

        if self._is_immediate_write():
            # "all" mode - clear folder and recreate
            try:
                if self.debug_dir.exists():
                    shutil.rmtree(self.debug_dir)
                self.debug_dir.mkdir(parents=True, exist_ok=True)
                logger.debug(f"[DebugLogger] Directory {self.debug_dir} cleared for new request.")
            except Exception as e:
                logger.error(f"[DebugLogger] Error preparing directory: {e}")

    def log_request_body(self, body: bytes):
        """
        Saves the request body (from client, OpenAI format).
        
        In "all" mode: writes immediately to file.
        In "errors" mode: buffers.
        """
        if not self._is_enabled():
            return

        if self._is_immediate_write():
            self._write_request_body_to_file(body)
        else:
            # "errors" mode - buffer
            self._request_body_buffer = body

    def log_kiro_request_body(self, body: bytes):
        """
        Saves the modified request body (to Kiro API).
        
        In "all" mode: writes immediately to file.
        In "errors" mode: buffers.
        """
        if not self._is_enabled():
            return

        if self._is_immediate_write():
            self._write_kiro_request_body_to_file(body)
        else:
            # "errors" mode - buffer
            self._kiro_request_body_buffer = body

    def log_raw_chunk(self, chunk: bytes):
        """
        Appends raw response chunk (from provider).
        
        In "all" mode: writes immediately to file.
        In "errors" mode: buffers.
        """
        if not self._is_enabled():
            return

        if self._is_immediate_write():
            self._append_raw_chunk_to_file(chunk)
        else:
            # "errors" mode - buffer
            self._raw_chunks_buffer.extend(chunk)

    def log_modified_chunk(self, chunk: bytes):
        """
        Appends modified chunk (to client).
        
        In "all" mode: writes immediately to file.
        In "errors" mode: buffers.
        """
        if not self._is_enabled():
            return

        if self._is_immediate_write():
            self._append_modified_chunk_to_file(chunk)
        else:
            # "errors" mode - buffer
            self._modified_chunks_buffer.extend(chunk)
    
    def record_anomaly(self, category: str, metadata: Optional[Dict[str, Any]] = None):
        """
        Records a protocol anomaly for the current request (metadata-only).

        Unlike request/response buffers, anomalies are persisted on BOTH the
        success and error paths, because an anomaly on an HTTP 200 response
        (e.g. a malformed tool call in an otherwise-successful stream) is
        precisely the case worth capturing.

        No raw payloads, prompts, or stream bytes are captured here — only a
        bounded category plus caller-supplied scalar metadata.

        Args:
            category: Short anomaly signature (e.g. "tool_protocol_failure").
            metadata: Optional flat dict of JSON-serializable scalars.
        """
        if not self._is_enabled():
            return

        entry: Dict[str, Any] = {"category": str(category)}
        if metadata:
            # Keep only scalar metadata to guarantee no payload leakage.
            for key, value in metadata.items():
                if isinstance(value, (str, int, float, bool)) or value is None:
                    entry[str(key)] = value
                else:
                    entry[str(key)] = repr(value)[:200]

        self._anomaly_buffer.append(entry)

    def log_error_info(self, status_code: int, error_message: str = ""):
        """
        Writes error information to file.
        
        Works in both modes (errors and all).
        In "all" mode writes immediately to file.
        In "errors" mode called from flush_on_error().
        
        Args:
            status_code: HTTP error status code
            error_message: Error message (optional)
        """
        if not self._is_enabled():
            return
        
        try:
            # Ensure directory exists
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            
            error_info = {
                "status_code": status_code,
                "error_message": error_message
            }
            error_file = self.debug_dir / "error_info.json"
            with open(error_file, "w", encoding="utf-8") as f:
                json.dump(error_info, f, indent=2, ensure_ascii=False)
            
            logger.debug(f"[DebugLogger] Error info saved (status={status_code})")
        except Exception as e:
            logger.error(f"[DebugLogger] Error writing error_info: {e}")

    def flush_on_error(self, status_code: int, error_message: str = ""):
        """
        Flushes buffers to files on error.
        
        In "errors" mode: flushes buffers and saves error_info.
        In "all" mode: only saves error_info (data already written).
        
        Args:
            status_code: HTTP error status code
            error_message: Error message (optional)
        """
        if not self._is_enabled():
            return
        
        # In "all" mode data is already written, add error_info and app logs
        if self._is_immediate_write():
            self.log_error_info(status_code, error_message)
            self._write_anomalies_to_file()
            self._write_app_logs_to_file()
            self._clear_app_logs_buffer()
            self._anomaly_buffer = []
            return

        # Check if there's anything to flush
        if not any([
            self._request_body_buffer,
            self._kiro_request_body_buffer,
            self._raw_chunks_buffer,
            self._modified_chunks_buffer,
            self._anomaly_buffer,
        ]):
            return
        
        try:
            # Create directory if not exists
            if self.debug_dir.exists():
                shutil.rmtree(self.debug_dir)
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            
            # Flush buffers to files
            if self._request_body_buffer:
                self._write_request_body_to_file(self._request_body_buffer)
            
            if self._kiro_request_body_buffer:
                self._write_kiro_request_body_to_file(self._kiro_request_body_buffer)
            
            if self._raw_chunks_buffer:
                file_path = self.debug_dir / "response_stream_raw.txt"
                with open(file_path, "wb") as f:
                    f.write(self._raw_chunks_buffer)
            
            if self._modified_chunks_buffer:
                file_path = self.debug_dir / "response_stream_modified.txt"
                with open(file_path, "wb") as f:
                    f.write(self._modified_chunks_buffer)
            
            # Save error information
            self.log_error_info(status_code, error_message)

            # Save protocol anomalies (metadata-only)
            self._write_anomalies_to_file()

            # Save application logs
            self._write_app_logs_to_file()

            logger.info(f"[DebugLogger] Error logs flushed to {self.debug_dir} (status={status_code})")
            
        except Exception as e:
            logger.error(f"[DebugLogger] Error flushing buffers: {e}")
        finally:
            # Clear buffers after flush
            self._clear_buffers()
    
    def discard_buffers(self):
        """
        Clears buffers without writing to files.
        
        Called when request completed successfully in "errors" mode.
        Also called in "all" mode to save logs of successful request.
        """
        if DEBUG_MODE == "errors":
            # Anomalies are persisted even on success, since a protocol anomaly
            # on an HTTP 200 response is exactly what we want to capture.
            # Everything else (prompts, requests, raw streams) is discarded.
            self._write_anomalies_to_file()
            self._clear_buffers()
        elif DEBUG_MODE == "all":
            # In "all" mode save logs even for successful requests
            self._write_anomalies_to_file()
            self._write_app_logs_to_file()
            self._clear_app_logs_buffer()
            self._anomaly_buffer = []
    
    # ==================== Private file writing methods ====================
    
    def _write_request_body_to_file(self, body: bytes):
        """Writes request body to file."""
        try:
            file_path = self.debug_dir / "request_body.json"
            try:
                json_obj = json.loads(body)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_obj, f, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                with open(file_path, "wb") as f:
                    f.write(body)
        except Exception as e:
            logger.error(f"[DebugLogger] Error writing request_body: {e}")
    
    def _write_kiro_request_body_to_file(self, body: bytes):
        """Writes Kiro request body to file."""
        try:
            file_path = self.debug_dir / "kiro_request_body.json"
            try:
                json_obj = json.loads(body)
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(json_obj, f, indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                with open(file_path, "wb") as f:
                    f.write(body)
        except Exception as e:
            logger.error(f"[DebugLogger] Error writing kiro_request_body: {e}")
    
    def _append_raw_chunk_to_file(self, chunk: bytes):
        """Appends raw chunk to file."""
        try:
            file_path = self.debug_dir / "response_stream_raw.txt"
            with open(file_path, "ab") as f:
                f.write(chunk)
        except Exception:
            pass
    
    def _append_modified_chunk_to_file(self, chunk: bytes):
        """Appends modified chunk to file."""
        try:
            file_path = self.debug_dir / "response_stream_modified.txt"
            with open(file_path, "ab") as f:
                f.write(chunk)
        except Exception:
            pass
    
    def _write_anomalies_to_file(self):
        """Writes accumulated protocol anomalies to anomaly_info.json (metadata-only)."""
        if not self._anomaly_buffer:
            return
        try:
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            file_path = self.debug_dir / "anomaly_info.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(
                    {"anomalies": self._anomaly_buffer},
                    f,
                    indent=2,
                    ensure_ascii=False,
                )
            logger.debug(
                f"[DebugLogger] Recorded {len(self._anomaly_buffer)} anomaly event(s)"
            )
        except Exception as e:
            logger.error(f"[DebugLogger] Error writing anomaly_info: {e}")

    def _write_app_logs_to_file(self):
        """Writes captured application logs to file."""
        try:
            # Get buffer contents
            logs_content = self._app_logs_buffer.getvalue()
            
            if not logs_content.strip():
                return
            
            # Ensure directory exists
            self.debug_dir.mkdir(parents=True, exist_ok=True)
            
            file_path = self.debug_dir / "app_logs.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(logs_content)
            
            logger.debug(f"[DebugLogger] App logs saved to {file_path}")
        except Exception as e:
            # Don't log error via logger to avoid recursion
            pass


# Global instance
debug_logger = DebugLogger()