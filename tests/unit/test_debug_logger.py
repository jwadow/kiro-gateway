# -*- coding: utf-8 -*-

"""
Unit-тесты для DebugLogger.
Проверяет логику буферизации и записи debug логов в разных режимах.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestDebugLoggerModeOff:
    """Тесты для режима DEBUG_MODE=off."""
    
    def test_prepare_new_request_does_nothing(self, tmp_path):
        """
        Что он делает: Проверяет, что prepare_new_request ничего не делает в режиме off.
        Цель: Убедиться, что в режиме off директория не создаётся.
        """
        print("Настройка: Режим off...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'off'):
            with patch('kiro.debug_logger.DEBUG_DIR', str(tmp_path / "debug_logs")):
                # Пересоздаём экземпляр с новыми настройками
                from kiro.debug_logger import DebugLogger
                logger = DebugLogger.__new__(DebugLogger)
                logger._initialized = False
                logger.__init__()
                logger.debug_dir = tmp_path / "debug_logs"
                
                print("Действие: Вызов prepare_new_request...")
                logger.prepare_new_request()
                
                print(f"Проверяем, что директория не создана...")
                assert not (tmp_path / "debug_logs").exists()
    
    def test_log_request_body_does_nothing(self, tmp_path):
        """
        Что он делает: Проверяет, что log_request_body ничего не делает в режиме off.
        Цель: Убедиться, что данные не записываются.
        """
        print("Настройка: Режим off...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'off'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = tmp_path / "debug_logs"
            
            print("Действие: Вызов log_request_body...")
            logger.log_request_body(b'{"test": "data"}')
            
            print(f"Проверяем, что файл не создан...")
            assert not (tmp_path / "debug_logs" / "request_body.json").exists()


class TestDebugLoggerModeAll:
    """Тесты для режима DEBUG_MODE=all."""
    
    def test_prepare_new_request_clears_directory(self, tmp_path):
        """
        Что он делает: Проверяет, что prepare_new_request очищает директорию в режиме all.
        Цель: Убедиться, что старые логи удаляются.
        """
        print("Настройка: Режим all, создаём старый файл...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        old_file = debug_dir / "old_file.txt"
        old_file.write_text("old content")
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов prepare_new_request...")
            logger.prepare_new_request()
            
            print(f"Проверяем, что старый файл удалён...")
            assert not old_file.exists()
            print(f"Проверяем, что директория существует...")
            assert debug_dir.exists()
    
    def test_log_request_body_writes_immediately(self, tmp_path):
        """
        Что он делает: Проверяет, что log_request_body пишет сразу в файл в режиме all.
        Цель: Убедиться, что данные записываются немедленно.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_request_body...")
            test_data = b'{"model": "test", "messages": []}'
            logger.log_request_body(test_data)
            
            print(f"Проверяем, что файл создан...")
            file_path = debug_dir / "request_body.json"
            assert file_path.exists()
            
            print(f"Проверяем содержимое файла...")
            content = json.loads(file_path.read_text())
            assert content["model"] == "test"
    
    def test_log_kiro_request_body_writes_immediately(self, tmp_path):
        """
        Что он делает: Проверяет, что log_kiro_request_body пишет сразу в файл в режиме all.
        Цель: Убедиться, что Kiro payload записывается немедленно.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_kiro_request_body...")
            test_data = b'{"conversationState": {}}'
            logger.log_kiro_request_body(test_data)
            
            print(f"Проверяем, что файл создан...")
            file_path = debug_dir / "kiro_request_body.json"
            assert file_path.exists()
    
    def test_log_raw_chunk_appends_to_file(self, tmp_path):
        """
        Что он делает: Проверяет, что log_raw_chunk дописывает в файл в режиме all.
        Цель: Убедиться, что чанки накапливаются.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_raw_chunk дважды...")
            logger.log_raw_chunk(b'chunk1')
            logger.log_raw_chunk(b'chunk2')
            
            print(f"Проверяем содержимое файла...")
            file_path = debug_dir / "response_stream_raw.txt"
            content = file_path.read_bytes()
            assert content == b'chunk1chunk2'


class TestDebugLoggerModeErrors:
    """Тесты для режима DEBUG_MODE=errors."""
    
    def test_log_request_body_buffers_data(self, tmp_path):
        """
        Что он делает: Проверяет, что log_request_body буферизует данные в режиме errors.
        Цель: Убедиться, что данные не записываются сразу.
        """
        print("Настройка: Режим errors...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_request_body...")
            test_data = b'{"test": "buffered"}'
            logger.log_request_body(test_data)
            
            print(f"Проверяем, что файл НЕ создан...")
            assert not debug_dir.exists()
            
            print(f"Проверяем, что данные в буфере...")
            assert logger._request_body_buffer == test_data
    
    def test_flush_on_error_writes_buffers(self, tmp_path):
        """
        Что он делает: Проверяет, что flush_on_error записывает буферы в файлы.
        Цель: Убедиться, что при ошибке данные сохраняются.
        """
        print("Настройка: Режим errors, заполняем буферы...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            # Заполняем буферы
            logger.log_request_body(b'{"request": "body"}')
            logger.log_kiro_request_body(b'{"kiro": "request"}')
            logger.log_raw_chunk(b'raw_chunk')
            logger.log_modified_chunk(b'modified_chunk')
            
            print("Действие: Вызов flush_on_error...")
            logger.flush_on_error(400, "Bad Request")
            
            print(f"Проверяем, что все файлы созданы...")
            assert (debug_dir / "request_body.json").exists()
            assert (debug_dir / "kiro_request_body.json").exists()
            assert (debug_dir / "response_stream_raw.txt").exists()
            assert (debug_dir / "response_stream_modified.txt").exists()
            assert (debug_dir / "error_info.json").exists()
            
            print(f"Проверяем error_info.json...")
            error_info = json.loads((debug_dir / "error_info.json").read_text())
            assert error_info["status_code"] == 400
            assert error_info["error_message"] == "Bad Request"
    
    def test_flush_on_error_clears_buffers(self, tmp_path):
        """
        Что он делает: Проверяет, что flush_on_error очищает буферы после записи.
        Цель: Убедиться, что буферы не накапливаются между запросами.
        """
        print("Настройка: Режим errors...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            logger.log_request_body(b'{"test": "data"}')
            
            print("Действие: Вызов flush_on_error...")
            logger.flush_on_error(500, "Error")
            
            print(f"Проверяем, что буферы очищены...")
            assert logger._request_body_buffer is None
            assert logger._kiro_request_body_buffer is None
            assert len(logger._raw_chunks_buffer) == 0
            assert len(logger._modified_chunks_buffer) == 0
    
    def test_discard_buffers_clears_without_writing(self, tmp_path):
        """
        Что он делает: Проверяет, что discard_buffers очищает буферы без записи.
        Цель: Убедиться, что успешные запросы не оставляют логов.
        """
        print("Настройка: Режим errors, заполняем буферы...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            logger.log_request_body(b'{"test": "data"}')
            logger.log_raw_chunk(b'chunk')
            
            print("Действие: Вызов discard_buffers...")
            logger.discard_buffers()
            
            print(f"Проверяем, что директория НЕ создана...")
            assert not debug_dir.exists()
            
            print(f"Проверяем, что буферы очищены...")
            assert logger._request_body_buffer is None
            assert len(logger._raw_chunks_buffer) == 0
    
    def test_flush_on_error_writes_error_info_in_mode_all(self, tmp_path):
        """
        Что он делает: Проверяет, что flush_on_error записывает error_info.json в режиме all.
        Цель: Убедиться, что информация об ошибке сохраняется в обоих режимах.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов flush_on_error...")
            logger.flush_on_error(400, "Bad Request")
            
            print(f"Проверяем, что error_info.json создан...")
            assert (debug_dir / "error_info.json").exists()
            
            print(f"Проверяем содержимое error_info.json...")
            error_info = json.loads((debug_dir / "error_info.json").read_text())
            assert error_info["status_code"] == 400
            assert error_info["error_message"] == "Bad Request"


class TestDebugLoggerLogErrorInfo:
    """Тесты для метода log_error_info()."""
    
    def test_log_error_info_writes_in_mode_all(self, tmp_path):
        """
        Что он делает: Проверяет, что log_error_info записывает файл в режиме all.
        Цель: Убедиться, что error_info.json создаётся при ошибках.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_error_info...")
            logger.log_error_info(500, "Internal Server Error")
            
            print(f"Проверяем, что error_info.json создан...")
            error_file = debug_dir / "error_info.json"
            assert error_file.exists()
            
            print(f"Проверяем содержимое...")
            error_info = json.loads(error_file.read_text())
            assert error_info["status_code"] == 500
            assert error_info["error_message"] == "Internal Server Error"
    
    def test_log_error_info_writes_in_mode_errors(self, tmp_path):
        """
        Что он делает: Проверяет, что log_error_info записывает файл в режиме errors.
        Цель: Убедиться, что метод работает в обоих режимах.
        """
        print("Настройка: Режим errors...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_error_info...")
            logger.log_error_info(404, "Not Found")
            
            print(f"Проверяем, что error_info.json создан...")
            error_file = debug_dir / "error_info.json"
            assert error_file.exists()
    
    def test_log_error_info_does_nothing_in_mode_off(self, tmp_path):
        """
        Что он делает: Проверяет, что log_error_info ничего не делает в режиме off.
        Цель: Убедиться, что в режиме off файлы не создаются.
        """
        print("Настройка: Режим off...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'off'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_error_info...")
            logger.log_error_info(500, "Error")
            
            print(f"Проверяем, что директория НЕ создана...")
            assert not debug_dir.exists()


class TestDebugLoggerHelperMethods:
    """Тесты для вспомогательных методов DebugLogger."""
    
    def test_is_enabled_returns_true_for_errors(self):
        """
        Что он делает: Проверяет _is_enabled() для режима errors.
        Цель: Убедиться, что режим errors считается включённым.
        """
        print("Настройка: Режим errors...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            
            print(f"Проверяем _is_enabled()...")
            assert logger._is_enabled() is True
    
    def test_is_enabled_returns_true_for_all(self):
        """
        Что он делает: Проверяет _is_enabled() для режима all.
        Цель: Убедиться, что режим all считается включённым.
        """
        print("Настройка: Режим all...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            
            print(f"Проверяем _is_enabled()...")
            assert logger._is_enabled() is True
    
    def test_is_enabled_returns_false_for_off(self):
        """
        Что он делает: Проверяет _is_enabled() для режима off.
        Цель: Убедиться, что режим off считается выключенным.
        """
        print("Настройка: Режим off...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'off'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            
            print(f"Проверяем _is_enabled()...")
            assert logger._is_enabled() is False
    
    def test_is_immediate_write_returns_true_for_all(self):
        """
        Что он делает: Проверяет _is_immediate_write() для режима all.
        Цель: Убедиться, что режим all пишет сразу.
        """
        print("Настройка: Режим all...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            
            print(f"Проверяем _is_immediate_write()...")
            assert logger._is_immediate_write() is True
    
    def test_is_immediate_write_returns_false_for_errors(self):
        """
        Что он делает: Проверяет _is_immediate_write() для режима errors.
        Цель: Убедиться, что режим errors буферизует.
        """
        print("Настройка: Режим errors...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            
            print(f"Проверяем _is_immediate_write()...")
            assert logger._is_immediate_write() is False


class TestDebugLoggerJsonHandling:
    """Тесты для обработки JSON в DebugLogger."""
    
    def test_log_request_body_writes_json_bytes_as_is(self, tmp_path):
        """
        What it does: Verifies JSON bodies are written byte-for-byte, without re-parsing.
        Purpose: Avoid a json.loads + indented json.dump per request in "all" mode.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_request_body с JSON...")
            logger.log_request_body(b'{"key":"value"}')
            
            print("Checking: file content is byte-identical to the input...")
            content = (debug_dir / "request_body.json").read_bytes()
            assert content == b'{"key":"value"}'
    
    def test_log_request_body_handles_invalid_json(self, tmp_path):
        """
        Что он делает: Проверяет обработку невалидного JSON.
        Цель: Убедиться, что невалидный JSON записывается как есть.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            logger = DebugLogger.__new__(DebugLogger)
            logger._initialized = False
            logger.__init__()
            logger.debug_dir = debug_dir
            
            print("Действие: Вызов log_request_body с невалидным JSON...")
            invalid_data = b'not a json {{'
            logger.log_request_body(invalid_data)
            
            print(f"Проверяем, что данные записаны как есть...")
            content = (debug_dir / "request_body.json").read_bytes()
            assert content == invalid_data


class TestDebugLoggerAppLogsCapture:
    """Тесты для захвата логов приложения (app_logs.txt)."""
    
    def test_prepare_new_request_sets_up_log_capture(self, tmp_path):
        """
        Что он делает: Проверяет, что prepare_new_request настраивает захват логов.
        Цель: Убедиться, что sink для логов создаётся.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = debug_dir
            
            print("Действие: Вызов prepare_new_request...")
            dbg_logger.prepare_new_request()
            
            print(f"Проверяем, что sink создан...")
            assert dbg_logger._loguru_sink_id is not None
            
            # Очистка
            dbg_logger._clear_app_logs_buffer()
    
    def test_flush_on_error_writes_app_logs_in_mode_errors(self, tmp_path):
        """
        Что он делает: Проверяет, что flush_on_error записывает app_logs.txt в режиме errors.
        Цель: Убедиться, что логи приложения сохраняются при ошибках.
        """
        print("Настройка: Режим errors...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            from loguru import logger as loguru_logger
            
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = debug_dir
            
            # Настраиваем захват логов
            dbg_logger.prepare_new_request()
            
            # Добавляем данные в буфер чтобы flush сработал
            dbg_logger.log_request_body(b'{"test": "data"}')
            
            # Пишем тестовый лог напрямую в буфер (имитация)
            dbg_logger._app_logs_buffer.write("Test log message\n")
            
            print("Действие: Вызов flush_on_error...")
            dbg_logger.flush_on_error(500, "Test Error")
            
            print(f"Проверяем, что app_logs.txt создан...")
            app_logs_file = debug_dir / "app_logs.txt"
            assert app_logs_file.exists()
            
            print(f"Проверяем содержимое...")
            content = app_logs_file.read_text()
            assert "Test log message" in content
    
    def test_discard_buffers_saves_logs_in_mode_all(self, tmp_path):
        """
        Что он делает: Проверяет, что discard_buffers сохраняет логи в режиме all.
        Цель: Убедиться, что даже успешные запросы сохраняют логи в режиме all.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = debug_dir
            
            # Настраиваем захват логов
            dbg_logger.prepare_new_request()
            
            # Пишем тестовый лог напрямую в буфер
            dbg_logger._app_logs_buffer.write("Success log message\n")
            
            print("Действие: Вызов discard_buffers...")
            dbg_logger.discard_buffers()
            
            print(f"Проверяем, что app_logs.txt создан...")
            app_logs_file = debug_dir / "app_logs.txt"
            assert app_logs_file.exists()
            
            print(f"Проверяем содержимое...")
            content = app_logs_file.read_text()
            assert "Success log message" in content
    
    def test_discard_buffers_does_not_save_logs_in_mode_errors(self, tmp_path):
        """
        Что он делает: Проверяет, что discard_buffers НЕ сохраняет логи в режиме errors.
        Цель: Убедиться, что успешные запросы не оставляют логов в режиме errors.
        """
        print("Настройка: Режим errors...")
        debug_dir = tmp_path / "debug_logs"
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            from kiro.debug_logger import DebugLogger
            
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = debug_dir
            
            # Настраиваем захват логов
            dbg_logger.prepare_new_request()
            
            # Пишем тестовый лог напрямую в буфер
            dbg_logger._app_logs_buffer.write("Should not be saved\n")
            
            print("Действие: Вызов discard_buffers...")
            dbg_logger.discard_buffers()
            
            print(f"Проверяем, что директория НЕ создана...")
            assert not debug_dir.exists()
    
    def test_clear_app_logs_buffer_removes_sink(self, tmp_path):
        """
        Что он делает: Проверяет, что _clear_app_logs_buffer удаляет sink.
        Цель: Убедиться, что sink корректно удаляется.
        """
        print("Настройка: Режим all...")
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = tmp_path / "debug_logs"
            
            # Настраиваем захват логов
            dbg_logger.prepare_new_request()
            sink_id = dbg_logger._loguru_sink_id
            assert sink_id is not None
            
            print("Действие: Вызов _clear_app_logs_buffer...")
            dbg_logger._clear_app_logs_buffer()
            
            print(f"Проверяем, что sink_id сброшен...")
            assert dbg_logger._loguru_sink_id is None
    
    def test_app_logs_not_saved_when_empty(self, tmp_path):
        """
        Что он делает: Проверяет, что пустые логи не создают файл.
        Цель: Убедиться, что app_logs.txt не создаётся если логов нет.
        """
        print("Настройка: Режим all...")
        debug_dir = tmp_path / "debug_logs"
        debug_dir.mkdir()
        
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            from kiro.debug_logger import DebugLogger
            
            dbg_logger = DebugLogger.__new__(DebugLogger)
            dbg_logger._initialized = False
            dbg_logger.__init__()
            dbg_logger.debug_dir = debug_dir
            
            # НЕ пишем ничего в буфер
            
            print("Действие: Вызов _write_app_logs_to_file...")
            dbg_logger._write_app_logs_to_file()
            
            print(f"Проверяем, что app_logs.txt НЕ создан...")
            app_logs_file = debug_dir / "app_logs.txt"
            assert not app_logs_file.exists()


def _fresh_debug_logger(debug_dir):
    """Build a non-singleton DebugLogger instance pointing at debug_dir."""
    from kiro.debug_logger import DebugLogger
    instance = DebugLogger.__new__(DebugLogger)
    instance._initialized = False
    instance.__init__()
    instance.debug_dir = debug_dir
    return instance


class TestDebugLoggerEnabledProperty:
    """Tests for the public `enabled` property."""

    @pytest.mark.parametrize("mode,expected", [("off", False), ("errors", True), ("all", True)])
    def test_enabled_matches_mode(self, tmp_path, mode, expected):
        """
        What it does: Reads `enabled` in each DEBUG_MODE.
        Purpose: Routes use it to skip serializing the Kiro payload when off.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', mode):
            instance = _fresh_debug_logger(tmp_path)
            assert instance.enabled is expected

    def test_enabled_is_read_only(self, tmp_path):
        """
        What it does: Tries to assign to `enabled`.
        Purpose: Mode is driven by config, not mutable per instance.
        """
        instance = _fresh_debug_logger(tmp_path)
        with pytest.raises(AttributeError):
            instance.enabled = True


class TestDebugLoggerRawBodies:
    """Tests that bodies are written as-is (no json re-parse / re-indent)."""

    def test_kiro_body_written_byte_identical(self, tmp_path):
        """
        What it does: Logs an already-indented Kiro body in "all" mode.
        Purpose: No second json.loads/json.dump pass.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            body = '{\n  "conversationState": {"x": "Привет"}\n}'.encode("utf-8")
            with patch('kiro.debug_logger.json.loads', side_effect=AssertionError("re-parsed")), \
                 patch('kiro.debug_logger.json.dump', side_effect=AssertionError("re-dumped")):
                instance.log_kiro_request_body(body)
            assert (tmp_path / "kiro_request_body.json").read_bytes() == body

    def test_errors_mode_flush_writes_bytes_as_is(self, tmp_path):
        """
        What it does: Buffers bodies in "errors" mode, then flushes.
        Purpose: Flushed files equal the logged bytes.
        """
        debug_dir = tmp_path / "dbg"
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            instance = _fresh_debug_logger(debug_dir)
            instance.log_request_body(b'{"a":1}')
            instance.log_kiro_request_body(b'{"b":2}')
            instance.flush_on_error(500, "x")
            assert (debug_dir / "request_body.json").read_bytes() == b'{"a":1}'
            assert (debug_dir / "kiro_request_body.json").read_bytes() == b'{"b":2}'

    def test_write_failure_is_logged_not_raised(self, tmp_path):
        """
        What it does: Writes into a directory that does not exist.
        Purpose: Debug logging never breaks a request.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path / "missing" / "deeper")
            instance.log_request_body(b'{}')  # must not raise


class TestDebugLoggerChunkFileHandles:
    """Tests for per-request chunk file handle reuse in "all" mode."""

    def test_single_open_per_file_per_request(self, tmp_path):
        """
        What it does: Logs many raw and modified chunks.
        Purpose: Each stream file is opened once, not once per chunk.
        """
        import builtins
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            real_open = builtins.open
            with patch('builtins.open', side_effect=real_open) as spy:
                for i in range(50):
                    instance.log_raw_chunk(f"r{i}".encode())
                    instance.log_modified_chunk(f"m{i}".encode())
            opened = [c.args[0] for c in spy.call_args_list]
            assert sum(1 for p in opened if str(p).endswith("response_stream_raw.txt")) == 1
            assert sum(1 for p in opened if str(p).endswith("response_stream_modified.txt")) == 1
            instance.discard_buffers()

    def test_content_visible_while_streaming(self, tmp_path):
        """
        What it does: Reads the file between chunks without closing.
        Purpose: Handle is flushed per chunk, so the file is usable during a stream.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            instance.log_raw_chunk(b'a')
            assert (tmp_path / "response_stream_raw.txt").read_bytes() == b'a'
            instance.log_raw_chunk(b'b')
            assert (tmp_path / "response_stream_raw.txt").read_bytes() == b'ab'
            instance.discard_buffers()

    def test_discard_closes_handles(self, tmp_path):
        """
        What it does: Finishes a successful request in "all" mode.
        Purpose: No file handles leak across requests.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            instance.log_raw_chunk(b'x')
            handles = list(instance._chunk_files.values())
            instance.discard_buffers()
            assert instance._chunk_files == {}
            assert all(h.closed for h in handles)

    def test_flush_on_error_closes_handles(self, tmp_path):
        """
        What it does: Finishes a failed request in "all" mode.
        Purpose: Handles closed before error_info is written.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            instance.log_modified_chunk(b'x')
            handles = list(instance._chunk_files.values())
            instance.flush_on_error(500, "boom")
            assert all(h.closed for h in handles)
            assert (tmp_path / "error_info.json").exists()

    def test_prepare_new_request_closes_handles_and_clears_dir(self, tmp_path):
        """
        What it does: Starts a new request while a previous stream left handles open.
        Purpose: rmtree works (Windows locks open files) and old chunks don't leak in.
        """
        debug_dir = tmp_path / "dbg"
        debug_dir.mkdir()
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(debug_dir)
            instance.log_raw_chunk(b'old')
            instance.prepare_new_request()
            assert instance._chunk_files == {}
            instance.log_raw_chunk(b'new')
            assert (debug_dir / "response_stream_raw.txt").read_bytes() == b'new'
            instance.discard_buffers()

    def test_reopens_after_external_close(self, tmp_path):
        """
        What it does: Closes a cached handle behind the logger's back.
        Purpose: A closed handle is replaced, not written to.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path)
            instance.log_raw_chunk(b'1')
            instance._chunk_files["response_stream_raw.txt"].close()
            instance.log_raw_chunk(b'2')
            assert (tmp_path / "response_stream_raw.txt").read_bytes() == b'12'
            instance.discard_buffers()

    def test_open_failure_is_swallowed(self, tmp_path):
        """
        What it does: Chunk file cannot be opened.
        Purpose: Streaming continues even if debug writes fail.
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'all'):
            instance = _fresh_debug_logger(tmp_path / "does-not-exist")
            instance.log_raw_chunk(b'x')  # must not raise
            assert instance._chunk_files == {}

    def test_close_error_is_swallowed(self, tmp_path):
        """
        What it does: A handle whose close() raises OSError.
        Purpose: Cleanup never raises into the request.
        """
        instance = _fresh_debug_logger(tmp_path)
        bad = MagicMock()
        bad.close.side_effect = OSError("disk gone")
        instance._chunk_files = {"f": bad}
        instance._close_chunk_files()
        assert instance._chunk_files == {}

    def test_errors_mode_does_not_open_files_per_chunk(self, tmp_path):
        """
        What it does: Logs chunks in "errors" mode.
        Purpose: Buffer mode still buffers in memory (no handles).
        """
        with patch('kiro.debug_logger.DEBUG_MODE', 'errors'):
            instance = _fresh_debug_logger(tmp_path)
            instance.log_raw_chunk(b'x')
            assert instance._chunk_files == {}
            assert bytes(instance._raw_chunks_buffer) == b'x'
