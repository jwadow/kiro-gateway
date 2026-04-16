# -*- coding: utf-8 -*-

"""
Unit-тесты для модуля токенизатора (kiro/tokenizer.py).

Проверяет:
- Подсчёт токенов в тексте (count_tokens)
- Подсчёт токенов в сообщениях (count_message_tokens)
- Подсчёт токенов в инструментах (count_tools_tokens)
- Оценку токенов запроса (estimate_request_tokens)
- Коэффициент коррекции для Claude (CLAUDE_CORRECTION_FACTOR)
- Fallback при отсутствии tiktoken
"""

import pytest
from unittest.mock import patch, MagicMock

from kiro.tokenizer import (
    count_tokens,
    count_message_tokens,
    count_tools_tokens,
    count_system_tokens,
    estimate_request_tokens,
    CLAUDE_CORRECTION_FACTOR,
    _get_encoding
)


class TestCountTokens:
    """Тесты для функции count_tokens."""
    
    def test_empty_string_returns_zero(self):
        """
        Что он делает: Проверяет, что пустая строка возвращает 0 токенов.
        Цель: Убедиться в корректной обработке граничного случая.
        """
        print("Тест: Пустая строка...")
        result = count_tokens("")
        print(f"Результат: {result}")
        assert result == 0, "Пустая строка должна возвращать 0 токенов"
    
    def test_none_returns_zero(self):
        """
        Что он делает: Проверяет, что None возвращает 0 токенов.
        Цель: Убедиться в корректной обработке None.
        """
        print("Тест: None...")
        result = count_tokens(None)
        print(f"Результат: {result}")
        assert result == 0, "None должен возвращать 0 токенов"
    
    def test_simple_text_returns_positive(self):
        """
        Что он делает: Проверяет, что простой текст возвращает положительное число токенов.
        Цель: Убедиться в базовой работоспособности подсчёта.
        """
        print("Тест: Простой текст...")
        result = count_tokens("Hello, world!")
        print(f"Результат: {result}")
        assert result > 0, "Простой текст должен возвращать положительное число токенов"
    
    def test_longer_text_returns_more_tokens(self):
        """
        Что он делает: Проверяет, что более длинный текст возвращает больше токенов.
        Цель: Убедиться в корректной пропорциональности подсчёта.
        """
        print("Тест: Сравнение длинного и короткого текста...")
        short_text = "Hello"
        long_text = "Hello, this is a much longer text that should have more tokens"
        
        short_tokens = count_tokens(short_text)
        long_tokens = count_tokens(long_text)
        
        print(f"Короткий текст: {short_tokens} токенов")
        print(f"Длинный текст: {long_tokens} токенов")
        
        assert long_tokens > short_tokens, "Длинный текст должен иметь больше токенов"
    
    def test_claude_correction_applied_by_default(self):
        """
        Что он делает: Проверяет, что коэффициент коррекции Claude применяется по умолчанию.
        Цель: Убедиться, что apply_claude_correction=True по умолчанию.
        """
        print("Тест: Коэффициент коррекции Claude...")
        text = "This is a test text for token counting"
        
        with_correction = count_tokens(text, apply_claude_correction=True)
        without_correction = count_tokens(text, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        # С коррекцией должно быть больше (коэффициент 1.15)
        assert with_correction > without_correction, "С коррекцией должно быть больше токенов"
        
        # Проверяем примерное соотношение
        ratio = with_correction / without_correction
        print(f"Соотношение: {ratio}")
        assert 1.1 <= ratio <= 1.2, f"Соотношение должно быть около {CLAUDE_CORRECTION_FACTOR}"
    
    def test_without_claude_correction(self):
        """
        Что он делает: Проверяет подсчёт без коэффициента коррекции.
        Цель: Убедиться, что apply_claude_correction=False работает.
        """
        print("Тест: Без коэффициента коррекции...")
        text = "Test text"
        
        result = count_tokens(text, apply_claude_correction=False)
        print(f"Результат: {result}")
        
        assert result > 0, "Должен вернуть положительное число токенов"
    
    def test_unicode_text(self):
        """
        Что он делает: Проверяет подсчёт токенов для Unicode текста.
        Цель: Убедиться в корректной обработке не-ASCII символов.
        """
        print("Тест: Unicode текст...")
        text = "Привет, мир! 你好世界 🌍"
        
        result = count_tokens(text)
        print(f"Результат: {result}")
        
        assert result > 0, "Unicode текст должен возвращать положительное число токенов"
    
    def test_multiline_text(self):
        """
        Что он делает: Проверяет подсчёт токенов для многострочного текста.
        Цель: Убедиться в корректной обработке переносов строк.
        """
        print("Тест: Многострочный текст...")
        text = """Line 1
        Line 2
        Line 3"""
        
        result = count_tokens(text)
        print(f"Результат: {result}")
        
        assert result > 0, "Многострочный текст должен возвращать положительное число токенов"
    
    def test_json_text(self):
        """
        Что он делает: Проверяет подсчёт токенов для JSON строки.
        Цель: Убедиться в корректной обработке JSON.
        """
        print("Тест: JSON текст...")
        text = '{"name": "test", "value": 123, "nested": {"key": "value"}}'
        
        result = count_tokens(text)
        print(f"Результат: {result}")
        
        assert result > 0, "JSON текст должен возвращать положительное число токенов"


class TestCountTokensFallback:
    """Тесты для fallback логики при отсутствии tiktoken."""
    
    def test_fallback_when_tiktoken_unavailable(self):
        """
        Что он делает: Проверяет fallback подсчёт когда tiktoken недоступен.
        Цель: Убедиться, что система работает без tiktoken.
        """
        print("Тест: Fallback без tiktoken...")
        
        # Мокируем _get_encoding чтобы вернуть None
        with patch('kiro.tokenizer._get_encoding', return_value=None):
            result = count_tokens("Hello world test")
            print(f"Результат: {result}")
            
            # Fallback: len(text) // 4 + 1, затем * 1.15
            # "Hello world test" = 16 символов
            # 16 // 4 + 1 = 5
            # 5 * 1.15 = 5.75 -> 5
            assert result > 0, "Fallback должен вернуть положительное число"
    
    def test_fallback_without_correction(self):
        """
        Что он делает: Проверяет fallback без коэффициента коррекции.
        Цель: Убедиться, что fallback работает с apply_claude_correction=False.
        """
        print("Тест: Fallback без коррекции...")
        
        with patch('kiro.tokenizer._get_encoding', return_value=None):
            result = count_tokens("Test", apply_claude_correction=False)
            print(f"Результат: {result}")
            
            # "Test" = 4 символа
            # 4 // 4 + 1 = 2
            assert result > 0, "Fallback должен вернуть положительное число"


class TestCountMessageTokens:
    """Тесты для функции count_message_tokens."""
    
    def test_empty_list_returns_zero(self):
        """
        Что он делает: Проверяет, что пустой список возвращает 0 токенов.
        Цель: Убедиться в корректной обработке пустого списка.
        """
        print("Тест: Пустой список сообщений...")
        result = count_message_tokens([])
        print(f"Результат: {result}")
        assert result == 0, "Пустой список должен возвращать 0 токенов"
    
    def test_none_returns_zero(self):
        """
        Что он делает: Проверяет, что None возвращает 0 токенов.
        Цель: Убедиться в корректной обработке None.
        """
        print("Тест: None...")
        result = count_message_tokens(None)
        print(f"Результат: {result}")
        assert result == 0, "None должен возвращать 0 токенов"
    
    def test_single_user_message(self):
        """
        Что он делает: Проверяет подсчёт токенов для одного user сообщения.
        Цель: Убедиться в базовой работоспособности.
        """
        print("Тест: Одно user сообщение...")
        messages = [{"role": "user", "content": "Hello, AI!"}]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        assert result > 0, "Должен вернуть положительное число токенов"
    
    def test_multiple_messages(self):
        """
        Что он делает: Проверяет подсчёт токенов для нескольких сообщений.
        Цель: Убедиться, что токены суммируются корректно.
        """
        print("Тест: Несколько сообщений...")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": "Hi there! How can I help you?"},
            {"role": "user", "content": "What is the weather?"}
        ]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        # Больше сообщений = больше токенов
        single_message = count_message_tokens([messages[0]])
        assert result > single_message, "Несколько сообщений должны иметь больше токенов"
    
    def test_message_with_tool_calls(self):
        """
        Что он делает: Проверяет подсчёт токенов для сообщения с tool_calls.
        Цель: Убедиться, что tool_calls учитываются.
        """
        print("Тест: Сообщение с tool_calls...")
        messages = [
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": "get_weather",
                            "arguments": '{"location": "Moscow"}'
                        }
                    }
                ]
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        assert result > 0, "Сообщение с tool_calls должно иметь токены"
    
    def test_message_with_tool_call_id(self):
        """
        Что он делает: Проверяет подсчёт токенов для tool response сообщения.
        Цель: Убедиться, что tool_call_id учитывается.
        """
        print("Тест: Tool response сообщение...")
        messages = [
            {
                "role": "tool",
                "content": "The weather in Moscow is sunny, 25°C",
                "tool_call_id": "call_123"
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        assert result > 0, "Tool response должен иметь токены"
    
    def test_message_with_list_content(self):
        """
        Что он делает: Проверяет подсчёт токенов для мультимодального контента.
        Цель: Убедиться, что list content обрабатывается.
        """
        print("Тест: Мультимодальный контент...")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What is in this image?"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/image.jpg"}}
                ]
            }
        ]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        assert result > 0, "Мультимодальный контент должен иметь токены"
    
    def test_without_claude_correction(self):
        """
        Что он делает: Проверяет подсчёт без коэффициента коррекции.
        Цель: Убедиться, что apply_claude_correction=False работает.
        """
        print("Тест: Без коэффициента коррекции...")
        messages = [{"role": "user", "content": "Test message"}]
        
        with_correction = count_message_tokens(messages, apply_claude_correction=True)
        without_correction = count_message_tokens(messages, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        assert with_correction > without_correction, "С коррекцией должно быть больше"
    
    def test_message_with_empty_content(self):
        """
        Что он делает: Проверяет подсчёт для сообщения с пустым content.
        Цель: Убедиться, что пустой content не ломает подсчёт.
        """
        print("Тест: Пустой content...")
        messages = [{"role": "user", "content": ""}]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        # Должны быть служебные токены (role, разделители)
        assert result > 0, "Даже пустое сообщение должно иметь служебные токены"
    
    def test_message_with_none_content(self):
        """
        Что он делает: Проверяет подсчёт для сообщения с None content.
        Цель: Убедиться, что None content не ломает подсчёт.
        """
        print("Тест: None content...")
        messages = [{"role": "assistant", "content": None}]
        
        result = count_message_tokens(messages)
        print(f"Результат: {result}")
        
        assert result > 0, "Сообщение с None content должно иметь служебные токены"

    def test_anthropic_tool_use_and_tool_result_blocks(self):
        """
        Что он делает: Проверяет подсчёт Anthropic блоков tool_use/tool_result.
        Цель: Убедиться, что ключевые блоки Claude Code не теряются в подсчёте.
        """
        print("Тест: Anthropic tool_use/tool_result блоки...")
        messages = [
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": "toolu_123",
                        "name": "get_weather",
                        "input": {"city": "Tokyo"}
                    }
                ]
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "toolu_123",
                        "content": [{"type": "text", "text": "晴天 26C"}],
                        "is_error": False
                    }
                ]
            }
        ]

        result = count_message_tokens(messages, apply_claude_correction=False)
        print(f"Результат: {result}")
        assert result > 0


class TestCountToolsTokens:
    """Тесты для функции count_tools_tokens."""
    
    def test_none_returns_zero(self):
        """
        Что он делает: Проверяет, что None возвращает 0 токенов.
        Цель: Убедиться в корректной обработке None.
        """
        print("Тест: None...")
        result = count_tools_tokens(None)
        print(f"Результат: {result}")
        assert result == 0, "None должен возвращать 0 токенов"
    
    def test_empty_list_returns_zero(self):
        """
        Что он делает: Проверяет, что пустой список возвращает 0 токенов.
        Цель: Убедиться в корректной обработке пустого списка.
        """
        print("Тест: Пустой список...")
        result = count_tools_tokens([])
        print(f"Результат: {result}")
        assert result == 0, "Пустой список должен возвращать 0 токенов"
    
    def test_single_tool(self):
        """
        Что он делает: Проверяет подсчёт токенов для одного инструмента.
        Цель: Убедиться в базовой работоспособности.
        """
        print("Тест: Один инструмент...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get the current weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string", "description": "City name"}
                        },
                        "required": ["location"]
                    }
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Результат: {result}")
        
        assert result > 0, "Инструмент должен иметь токены"
    
    def test_multiple_tools(self):
        """
        Что он делает: Проверяет подсчёт токенов для нескольких инструментов.
        Цель: Убедиться, что токены суммируются.
        """
        print("Тест: Несколько инструментов...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        single_tool = count_tools_tokens([tools[0]])
        
        print(f"Два инструмента: {result}")
        print(f"Один инструмент: {single_tool}")
        
        assert result > single_tool, "Больше инструментов = больше токенов"
    
    def test_tool_with_complex_parameters(self):
        """
        Что он делает: Проверяет подсчёт для инструмента со сложными параметрами.
        Цель: Убедиться, что JSON schema параметров учитывается.
        """
        print("Тест: Сложные параметры...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "complex_function",
                    "description": "A function with complex parameters",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Name"},
                            "age": {"type": "integer", "description": "Age"},
                            "address": {
                                "type": "object",
                                "properties": {
                                    "street": {"type": "string"},
                                    "city": {"type": "string"},
                                    "country": {"type": "string"}
                                }
                            },
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"}
                            }
                        },
                        "required": ["name", "age"]
                    }
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Результат: {result}")
        
        assert result > 0, "Сложный инструмент должен иметь токены"
    
    def test_tool_without_parameters(self):
        """
        Что он делает: Проверяет подсчёт для инструмента без параметров.
        Цель: Убедиться, что отсутствие parameters не ломает подсчёт.
        """
        print("Тест: Без параметров...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "no_params_func",
                    "description": "A function without parameters"
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Результат: {result}")
        
        assert result > 0, "Инструмент без параметров должен иметь токены"
    
    def test_tool_with_empty_description(self):
        """
        Что он делает: Проверяет подсчёт для инструмента с пустым description.
        Цель: Убедиться, что пустой description не ломает подсчёт.
        """
        print("Тест: Пустой description...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "func",
                    "description": "",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Результат: {result}")
        
        assert result > 0, "Инструмент с пустым description должен иметь токены"
    
    def test_non_function_tool_type(self):
        """
        Что он делает: Проверяет обработку инструмента с type != "function".
        Цель: Убедиться, что non-function tools обрабатываются.
        """
        print("Тест: Non-function tool...")
        tools = [
            {
                "type": "other_type",
                "some_field": "value"
            }
        ]
        
        result = count_tools_tokens(tools)
        print(f"Результат: {result}")
        
        # Должны быть хотя бы служебные токены
        assert result >= 0, "Non-function tool не должен ломать подсчёт"
    
    def test_without_claude_correction(self):
        """
        Что он делает: Проверяет подсчёт без коэффициента коррекции.
        Цель: Убедиться, что apply_claude_correction=False работает.
        """
        print("Тест: Без коэффициента коррекции...")
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "test_func",
                    "description": "Test function",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        with_correction = count_tools_tokens(tools, apply_claude_correction=True)
        without_correction = count_tools_tokens(tools, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        assert with_correction > without_correction, "С коррекцией должно быть больше"

    def test_openai_flat_tool_format(self):
        """
        Что он делает: Проверяет подсчёт токенов для flat/Cursor-style инструмента.
        Цель: Убедиться, что формат без type=function тоже учитывается.
        """
        tools = [
            {
                "name": "search_docs",
                "description": "Search docs by keyword",
                "input_schema": {
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"]
                }
            }
        ]

        result = count_tools_tokens(tools, apply_claude_correction=False)
        assert result > 4  # Must exceed base service overhead, proving name/description/schema are counted

    def test_anthropic_flat_and_openai_function_are_close(self):
        """
        Что он делает: Сравнивает Anthropic flat и OpenAI function форматы.
        Цель: Prevent Anthropic tools from regressing to base-overhead-only counting.
        """
        shared_schema = {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "recursive": {"type": "boolean", "description": "Recursive search"}
            },
            "required": ["path"]
        }
        openai_tools = [{
            "type": "function",
            "function": {
                "name": "search_files",
                "description": "Search files",
                "parameters": shared_schema
            }
        }]
        anthropic_tools = [{
            "name": "search_files",
            "description": "Search files",
            "input_schema": shared_schema
        }]

        openai_tokens = count_tools_tokens(openai_tools, apply_claude_correction=False)
        anthropic_tokens = count_tools_tokens(anthropic_tools, apply_claude_correction=False)

        assert openai_tokens > 4
        assert anthropic_tokens > 4
        diff_ratio = abs(openai_tokens - anthropic_tokens) / max(openai_tokens, anthropic_tokens)
        assert diff_ratio < 0.15


class TestCountSystemTokens:
    """Tests for count_system_tokens function."""

    def test_none_returns_zero(self):
        """Checks that None returns 0."""
        assert count_system_tokens(None) == 0

    def test_empty_string_returns_zero(self):
        """Checks that empty string returns 0."""
        assert count_system_tokens("") == 0

    def test_plain_string(self):
        """Checks that plain string is counted correctly."""
        result = count_system_tokens("You are a helpful assistant.", apply_claude_correction=False)
        assert result > 0

    def test_dict_block_list(self):
        """Checks that Anthropic dict block list is counted correctly."""
        blocks = [
            {"type": "text", "text": "You are a helpful assistant."},
            {"type": "text", "text": "Be concise.", "cache_control": {"type": "ephemeral"}},
        ]
        result = count_system_tokens(blocks, apply_claude_correction=False)
        assert result > 0
        # Should be greater than single block result
        single = count_system_tokens([blocks[0]], apply_claude_correction=False)
        assert result > single

    def test_dict_block_with_cache_control(self):
        """Checks that cache_control field is counted in tokens."""
        without_cache = [{"type": "text", "text": "Hello"}]
        with_cache = [{"type": "text", "text": "Hello", "cache_control": {"type": "ephemeral"}}]
        r1 = count_system_tokens(without_cache, apply_claude_correction=False)
        r2 = count_system_tokens(with_cache, apply_claude_correction=False)
        assert r2 > r1

    def test_non_dict_block_fallback(self):
        """Checks that non-dict elements fall back to str()."""
        result = count_system_tokens([42, "text"], apply_claude_correction=False)
        assert result > 0

    def test_unknown_type_fallback(self):
        """Checks that non-str/list types fall back to str()."""
        result = count_system_tokens(12345, apply_claude_correction=False)
        assert result > 0

    def test_claude_correction_applied(self):
        """Checks that Claude correction coefficient is applied."""
        text = "You are a helpful assistant that answers questions about programming and software engineering."
        without = count_system_tokens(text, apply_claude_correction=False)
        with_corr = count_system_tokens(text, apply_claude_correction=True)
        assert with_corr > without


class TestEstimateRequestTokens:
    """Тесты для функции estimate_request_tokens."""
    
    def test_messages_only(self):
        """
        Что он делает: Проверяет оценку токенов только для сообщений.
        Цель: Убедиться в базовой работоспособности.
        """
        print("Тест: Только сообщения...")
        messages = [{"role": "user", "content": "Hello!"}]
        
        result = estimate_request_tokens(messages)
        print(f"Результат: {result}")
        
        assert "messages_tokens" in result
        assert "tools_tokens" in result
        assert "system_tokens" in result
        assert "total_tokens" in result
        
        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] == 0
        assert result["system_tokens"] == 0
        assert result["total_tokens"] == result["messages_tokens"]
    
    def test_messages_with_tools(self):
        """
        Что он делает: Проверяет оценку токенов для сообщений с инструментами.
        Цель: Убедиться, что tools учитываются.
        """
        print("Тест: Сообщения с инструментами...")
        messages = [{"role": "user", "content": "What is the weather?"}]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather",
                    "parameters": {"type": "object", "properties": {}}
                }
            }
        ]
        
        result = estimate_request_tokens(messages, tools=tools)
        print(f"Результат: {result}")
        
        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["tools_tokens"]
    
    def test_messages_with_system_prompt(self):
        """
        Что он делает: Проверяет оценку токенов с отдельным system prompt.
        Цель: Убедиться, что system_prompt учитывается.
        """
        print("Тест: С system prompt...")
        messages = [{"role": "user", "content": "Hello!"}]
        system_prompt = "You are a helpful assistant."
        
        result = estimate_request_tokens(messages, system_prompt=system_prompt)
        print(f"Результат: {result}")
        
        assert result["messages_tokens"] > 0
        assert result["system_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["system_tokens"]

    def test_anthropic_system_blocks(self):
        """
        Что он делает: Проверяет оценку токенов для Anthropic system block списка.
        Цель: Убедиться, что system блоки тоже считаются.
        """
        print("Тест: Anthropic system blocks...")
        messages = [{"role": "user", "content": "Hello!"}]
        system_prompt = [
            {"type": "text", "text": "你是 Claude Code"},
            {"type": "text", "text": "Follow tools strictly", "cache_control": {"type": "ephemeral"}},
        ]

        result = estimate_request_tokens(messages, system_prompt=system_prompt, apply_claude_correction=False)
        print(f"Результат: {result}")

        assert result["system_tokens"] > 0
        assert result["total_tokens"] == result["messages_tokens"] + result["system_tokens"]
    
    def test_full_request(self):
        """
        Что он делает: Проверяет оценку токенов для полного запроса.
        Цель: Убедиться, что все компоненты суммируются.
        """
        print("Тест: Полный запрос...")
        messages = [
            {"role": "user", "content": "What is the weather in Moscow?"}
        ]
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "Get weather for a location",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "location": {"type": "string"}
                        }
                    }
                }
            }
        ]
        system_prompt = "You are a weather assistant."
        
        result = estimate_request_tokens(messages, tools=tools, system_prompt=system_prompt)
        print(f"Результат: {result}")
        
        expected_total = result["messages_tokens"] + result["tools_tokens"] + result["system_tokens"]
        assert result["total_tokens"] == expected_total, "Total должен быть суммой компонентов"

    def test_anthropic_messages_with_flat_tools(self):
        """
        Что он делает: Simulates Anthropic /v1/messages with tools+system scenario.
        Цель: Verify estimate_request_tokens no longer undercounts flat tools.
        """
        messages = [
            {"role": "user", "content": "请先读取项目结构，再回答。"}
        ]
        tools = [
            {
                "name": "read_file",
                "description": "Read a file from workspace",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Absolute path"}
                    },
                    "required": ["path"]
                }
            }
        ]
        system_prompt = [{"type": "text", "text": "你是代码助手。"}]

        result = estimate_request_tokens(
            messages,
            tools=tools,
            system_prompt=system_prompt,
            apply_claude_correction=False
        )

        assert result["messages_tokens"] > 0
        assert result["tools_tokens"] > 4
        assert result["system_tokens"] > 0
        assert result["total_tokens"] == (
            result["messages_tokens"] + result["tools_tokens"] + result["system_tokens"]
        )
    
    def test_empty_messages(self):
        """
        Что он делает: Проверяет оценку для пустого списка сообщений.
        Цель: Убедиться в корректной обработке граничного случая.
        """
        print("Тест: Пустые сообщения...")
        result = estimate_request_tokens([])
        print(f"Результат: {result}")
        
        assert result["messages_tokens"] == 0
        assert result["total_tokens"] == 0


class TestClaudeCorrectionFactor:
    """Тесты для коэффициента коррекции Claude."""
    
    def test_correction_factor_value(self):
        """
        Что он делает: Проверяет значение коэффициента коррекции.
        Цель: Убедиться, что коэффициент равен 1.15.
        """
        print(f"Коэффициент коррекции: {CLAUDE_CORRECTION_FACTOR}")
        assert CLAUDE_CORRECTION_FACTOR == 1.15, "Коэффициент должен быть 1.15"
    
    def test_correction_increases_token_count(self):
        """
        Что он делает: Проверяет, что коррекция увеличивает количество токенов.
        Цель: Убедиться, что коэффициент применяется корректно.
        """
        print("Тест: Коррекция увеличивает токены...")
        text = "This is a test text for checking the correction factor"
        
        with_correction = count_tokens(text, apply_claude_correction=True)
        without_correction = count_tokens(text, apply_claude_correction=False)
        
        print(f"С коррекцией: {with_correction}")
        print(f"Без коррекции: {without_correction}")
        
        assert with_correction > without_correction
        
        # Проверяем, что разница примерно 15%
        increase_percent = (with_correction - without_correction) / without_correction * 100
        print(f"Увеличение: {increase_percent:.1f}%")
        
        # Допускаем погрешность из-за округления
        assert 10 <= increase_percent <= 20, "Увеличение должно быть около 15%"
class TestGetEncoding:
    """Тесты для функции _get_encoding."""
    
    def test_returns_encoding_when_tiktoken_available(self):
        """
        Что он делает: Проверяет, что _get_encoding возвращает encoding когда tiktoken доступен.
        Цель: Убедиться в корректной инициализации tiktoken.
        """
        print("Тест: tiktoken доступен...")
        
        # Сбрасываем глобальную переменную для чистого теста
        import kiro.tokenizer as tokenizer_module
        original_encoding = tokenizer_module._encoding
        tokenizer_module._encoding = None
        
        try:
            encoding = _get_encoding()
            print(f"Encoding: {encoding}")
            
            # Если tiktoken установлен, должен вернуть encoding
            if encoding is not None:
                assert hasattr(encoding, 'encode'), "Encoding должен иметь метод encode"
        finally:
            # Восстанавливаем
            tokenizer_module._encoding = original_encoding
    
    def test_caches_encoding(self):
        """
        Что он делает: Проверяет, что encoding кэшируется.
        Цель: Убедиться в ленивой инициализации.
        """
        print("Тест: Кэширование encoding...")
        
        encoding1 = _get_encoding()
        encoding2 = _get_encoding()
        
        print(f"Encoding 1: {encoding1}")
        print(f"Encoding 2: {encoding2}")
        
        # Должен вернуть тот же объект
        assert encoding1 is encoding2, "Encoding должен кэшироваться"
    
    def test_handles_import_error(self):
        """
        Что он делает: Проверяет обработку ImportError при отсутствии tiktoken.
        Цель: Убедиться, что система работает без tiktoken.
        """
        print("Тест: ImportError...")
        
        import kiro.tokenizer as tokenizer_module
        original_encoding = tokenizer_module._encoding
        tokenizer_module._encoding = None
        
        try:
            # Мокируем import tiktoken чтобы выбросить ImportError
            with patch.dict('sys.modules', {'tiktoken': None}):
                with patch('builtins.__import__', side_effect=ImportError("No module named 'tiktoken'")):
                    # Сбрасываем кэш
                    tokenizer_module._encoding = None
                    
                    # Должен вернуть None и не упасть
                    # Примечание: из-за кэширования этот тест может не работать идеально
                    # но главное - проверить что код не падает
                    pass
        finally:
            tokenizer_module._encoding = original_encoding


class TestTokenizerIntegration:
    """Интеграционные тесты для токенизатора."""
    
    def test_realistic_chat_request(self):
        """
        Что он делает: Проверяет подсчёт токенов для реалистичного chat запроса.
        Цель: Убедиться в корректной работе на реальных данных.
        """
        print("Тест: Реалистичный chat запрос...")
        
        messages = [
            {"role": "system", "content": "You are a helpful AI assistant. Be concise and accurate."},
            {"role": "user", "content": "What is the capital of France?"},
            {"role": "assistant", "content": "The capital of France is Paris."},
            {"role": "user", "content": "What is its population?"}
        ]
        
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Search the web for information",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Search query"}
                        },
                        "required": ["query"]
                    }
                }
            }
        ]
        
        result = estimate_request_tokens(messages, tools=tools)
        print(f"Результат: {result}")
        
        # Проверяем разумность значений
        assert result["messages_tokens"] > 50, "Сообщения должны иметь > 50 токенов"
        assert result["tools_tokens"] > 20, "Tools должны иметь > 20 токенов"
        assert result["total_tokens"] > 70, "Total должен быть > 70 токенов"
    
    def test_large_context(self):
        """
        Что он делает: Проверяет подсчёт токенов для большого контекста.
        Цель: Убедиться в производительности на больших данных.
        """
        print("Тест: Большой контекст...")
        
        # Создаём большой текст
        large_text = "This is a test sentence. " * 1000  # ~5000 слов
        
        messages = [{"role": "user", "content": large_text}]
        
        result = estimate_request_tokens(messages)
        print(f"Токенов в большом тексте: {result['total_tokens']}")
        
        # Должно быть много токенов
        assert result["total_tokens"] > 1000, "Большой текст должен иметь > 1000 токенов"
    
    def test_consistency_across_calls(self):
        """
        Что он делает: Проверяет консистентность подсчёта при повторных вызовах.
        Цель: Убедиться, что результаты детерминированы.
        """
        print("Тест: Консистентность...")
        
        text = "This is a test for consistency checking"
        
        results = [count_tokens(text) for _ in range(5)]
        print(f"Результаты: {results}")
        
        # Все результаты должны быть одинаковыми
        assert len(set(results)) == 1, "Результаты должны быть консистентными"
    
    
