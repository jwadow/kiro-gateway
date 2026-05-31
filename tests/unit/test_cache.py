# -*- coding: utf-8 -*-

"""
Unit-тесты для ModelInfoCache.
Проверяет логику кэширования метаданных моделей.
"""

import asyncio
import time
import pytest

from kiro.cache import ModelInfoCache
from kiro.config import DEFAULT_MAX_INPUT_TOKENS


class TestModelInfoCacheInitialization:
    """Тесты инициализации ModelInfoCache."""
    
    def test_initialization_creates_empty_cache(self):
        """
        Что он делает: Проверяет, что кэш создаётся пустым.
        Цель: Убедиться в корректной инициализации.
        """
        print("Настройка: Создание ModelInfoCache...")
        cache = ModelInfoCache()
        
        print("Проверка: Кэш пуст при создании...")
        print(f"Сравниваем is_empty(): Ожидалось True, Получено {cache.is_empty()}")
        assert cache.is_empty() is True
        
        print(f"Сравниваем size: Ожидалось 0, Получено {cache.size}")
        assert cache.size == 0
    
    def test_initialization_with_custom_ttl(self):
        """
        Что он делает: Проверяет создание кэша с кастомным TTL.
        Цель: Убедиться, что TTL можно настроить.
        """
        print("Настройка: Создание ModelInfoCache с TTL=7200...")
        cache = ModelInfoCache(cache_ttl=7200)
        
        print("Проверка: TTL установлен корректно...")
        print(f"Сравниваем _cache_ttl: Ожидалось 7200, Получено {cache._cache_ttl}")
        assert cache._cache_ttl == 7200
    
    def test_initialization_last_update_is_none(self):
        """
        Что он делает: Проверяет, что last_update_time изначально None.
        Цель: Убедиться, что время обновления не установлено до первого update.
        """
        print("Настройка: Создание ModelInfoCache...")
        cache = ModelInfoCache()
        
        print("Проверка: last_update_time изначально None...")
        print(f"Сравниваем last_update_time: Ожидалось None, Получено {cache.last_update_time}")
        assert cache.last_update_time is None


class TestModelInfoCacheUpdate:
    """Тесты обновления кэша."""
    
    @pytest.mark.asyncio
    async def test_update_populates_cache(self, sample_models_data):
        """
        Что он делает: Проверяет заполнение кэша данными.
        Цель: Убедиться, что update() корректно сохраняет модели.
        """
        print("Настройка: Создание ModelInfoCache...")
        cache = ModelInfoCache()
        
        print(f"Действие: Обновление кэша с {len(sample_models_data)} моделями...")
        await cache.update(sample_models_data)
        
        print("Проверка: Кэш заполнен...")
        print(f"Сравниваем is_empty(): Ожидалось False, Получено {cache.is_empty()}")
        assert cache.is_empty() is False
        
        print(f"Сравниваем size: Ожидалось {len(sample_models_data)}, Получено {cache.size}")
        assert cache.size == len(sample_models_data)
    
    @pytest.mark.asyncio
    async def test_update_sets_last_update_time(self, sample_models_data):
        """
        Что он делает: Проверяет установку времени последнего обновления.
        Цель: Убедиться, что last_update_time устанавливается после update.
        """
        print("Настройка: Создание ModelInfoCache...")
        cache = ModelInfoCache()
        
        before_update = time.time()
        print(f"Действие: Обновление кэша (время до: {before_update})...")
        await cache.update(sample_models_data)
        after_update = time.time()
        
        print("Проверка: last_update_time установлен в разумных пределах...")
        print(f"last_update_time: {cache.last_update_time}")
        assert cache.last_update_time is not None
        assert before_update <= cache.last_update_time <= after_update
    
    @pytest.mark.asyncio
    async def test_update_replaces_existing_data(self, sample_models_data):
        """
        Что он делает: Проверяет замену данных при повторном update.
        Цель: Убедиться, что старые данные полностью заменяются.
        """
        print("Настройка: Создание ModelInfoCache и первое обновление...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Обновление с новыми данными...")
        new_data = [{"modelId": "new-model", "tokenLimits": {"maxInputTokens": 50000}}]
        await cache.update(new_data)
        
        print("Проверка: Старые данные заменены...")
        print(f"Сравниваем size: Ожидалось 1, Получено {cache.size}")
        assert cache.size == 1
        
        print("Проверка: Старая модель недоступна...")
        assert cache.get("claude-sonnet-4") is None
        
        print("Проверка: Новая модель доступна...")
        assert cache.get("new-model") is not None
    
    @pytest.mark.asyncio
    async def test_update_with_empty_list(self):
        """
        Что он делает: Проверяет обновление пустым списком.
        Цель: Убедиться, что кэш очищается при пустом update.
        """
        print("Настройка: Создание ModelInfoCache с данными...")
        cache = ModelInfoCache()
        await cache.update([{"modelId": "test-model"}])
        
        print("Действие: Обновление пустым списком...")
        await cache.update([])
        
        print("Проверка: Кэш пуст...")
        print(f"Сравниваем is_empty(): Ожидалось True, Получено {cache.is_empty()}")
        assert cache.is_empty() is True


class TestModelInfoCacheGet:
    """Тесты получения данных из кэша."""
    
    @pytest.mark.asyncio
    async def test_get_returns_model_info(self, sample_models_data):
        """
        Что он делает: Проверяет получение информации о модели.
        Цель: Убедиться, что get() возвращает корректные данные.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Получение информации о claude-sonnet-4...")
        model_info = cache.get("claude-sonnet-4")
        
        print("Проверка: Информация получена...")
        print(f"model_info: {model_info}")
        assert model_info is not None
        assert model_info["modelId"] == "claude-sonnet-4"
    
    @pytest.mark.asyncio
    async def test_get_returns_none_for_unknown_model(self, sample_models_data):
        """
        Что он делает: Проверяет возврат None для неизвестной модели.
        Цель: Убедиться, что get() не падает при отсутствии модели.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Получение информации о несуществующей модели...")
        model_info = cache.get("non-existent-model")
        
        print("Проверка: Возвращён None...")
        print(f"Сравниваем model_info: Ожидалось None, Получено {model_info}")
        assert model_info is None
    
    def test_get_from_empty_cache(self):
        """
        Что он делает: Проверяет get() из пустого кэша.
        Цель: Убедиться, что пустой кэш не вызывает ошибок.
        """
        print("Настройка: Создание пустого кэша...")
        cache = ModelInfoCache()
        
        print("Действие: Получение из пустого кэша...")
        model_info = cache.get("any-model")
        
        print("Проверка: Возвращён None...")
        print(f"Сравниваем model_info: Ожидалось None, Получено {model_info}")
        assert model_info is None


class TestModelInfoCacheGetMaxInputTokens:
    """Тесты получения maxInputTokens."""
    
    @pytest.mark.asyncio
    async def test_get_max_input_tokens_returns_value(self, sample_models_data):
        """
        Что он делает: Проверяет получение maxInputTokens для модели.
        Цель: Убедиться, что значение извлекается из tokenLimits.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Получение maxInputTokens для claude-sonnet-4...")
        max_tokens = cache.get_max_input_tokens("claude-sonnet-4")
        
        print("Проверка: Значение корректно...")
        print(f"Сравниваем max_tokens: Ожидалось 200000, Получено {max_tokens}")
        assert max_tokens == 200000
    
    @pytest.mark.asyncio
    async def test_get_max_input_tokens_returns_default_for_unknown(self, sample_models_data):
        """
        Что он делает: Проверяет возврат дефолта для неизвестной модели.
        Цель: Убедиться, что возвращается DEFAULT_MAX_INPUT_TOKENS.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Получение maxInputTokens для неизвестной модели...")
        max_tokens = cache.get_max_input_tokens("unknown-model")
        
        print("Проверка: Возвращён дефолт...")
        print(f"Сравниваем max_tokens: Ожидалось {DEFAULT_MAX_INPUT_TOKENS}, Получено {max_tokens}")
        assert max_tokens == DEFAULT_MAX_INPUT_TOKENS
    
    @pytest.mark.asyncio
    async def test_get_max_input_tokens_returns_default_when_no_token_limits(self):
        """
        Что он делает: Проверяет возврат дефолта при отсутствии tokenLimits.
        Цель: Убедиться, что модель без tokenLimits не ломает логику.
        """
        print("Настройка: Создание кэша с моделью без tokenLimits...")
        cache = ModelInfoCache()
        await cache.update([{"modelId": "model-without-limits"}])
        
        print("Действие: Получение maxInputTokens...")
        max_tokens = cache.get_max_input_tokens("model-without-limits")
        
        print("Проверка: Возвращён дефолт...")
        print(f"Сравниваем max_tokens: Ожидалось {DEFAULT_MAX_INPUT_TOKENS}, Получено {max_tokens}")
        assert max_tokens == DEFAULT_MAX_INPUT_TOKENS
    
    @pytest.mark.asyncio
    async def test_get_max_input_tokens_returns_default_when_max_input_is_none(self):
        """
        Что он делает: Проверяет возврат дефолта при maxInputTokens=None.
        Цель: Убедиться, что None в tokenLimits обрабатывается корректно.
        """
        print("Настройка: Создание кэша с моделью с maxInputTokens=None...")
        cache = ModelInfoCache()
        await cache.update([{
            "modelId": "model-with-null",
            "tokenLimits": {"maxInputTokens": None}
        }])
        
        print("Действие: Получение maxInputTokens...")
        max_tokens = cache.get_max_input_tokens("model-with-null")
        
        print("Проверка: Возвращён дефолт...")
        print(f"Сравниваем max_tokens: Ожидалось {DEFAULT_MAX_INPUT_TOKENS}, Получено {max_tokens}")
        assert max_tokens == DEFAULT_MAX_INPUT_TOKENS

    @pytest.mark.asyncio
    async def test_get_token_limits_returns_raw_limits(self, sample_models_data):
        """
        What it does: get_token_limits returns the raw maxInputTokens/maxOutputTokens.
        Purpose: PR #156 - /v1/models exposes real per-model ceilings, so callers
        can distinguish a real limit from the DEFAULT_MAX_INPUT_TOKENS fallback.
        """
        cache = ModelInfoCache()
        await cache.update([{
            "modelId": "claude-sonnet-4",
            "tokenLimits": {"maxInputTokens": 200000, "maxOutputTokens": 8192},
        }])

        limits = cache.get_token_limits("claude-sonnet-4")
        assert limits == {"maxInputTokens": 200000, "maxOutputTokens": 8192}

    @pytest.mark.asyncio
    async def test_get_token_limits_none_for_unknown_or_missing(self):
        """
        What it does: get_token_limits returns None for unknown models or models
        without tokenLimits (no DEFAULT fallback, unlike get_max_input_tokens).
        Purpose: Let callers treat "unknown" distinctly from "default".
        """
        cache = ModelInfoCache()
        await cache.update([{"modelId": "no-limits"}])

        assert cache.get_token_limits("unknown-model") is None
        assert cache.get_token_limits("no-limits") is None

    @pytest.mark.asyncio
    async def test_get_token_limits_ignores_non_int_values(self):
        """
        What it does: Non-integer tokenLimits values are dropped.
        Purpose: Guard against malformed upstream metadata leaking into the API.
        """
        cache = ModelInfoCache()
        await cache.update([{
            "modelId": "partial",
            "tokenLimits": {"maxInputTokens": 100000, "maxOutputTokens": None},
        }])

        limits = cache.get_token_limits("partial")
        assert limits == {"maxInputTokens": 100000}


class TestModelInfoCacheIsEmpty:
    """Тесты проверки пустоты кэша."""
    
    def test_is_empty_returns_true_for_new_cache(self):
        """
        Что он делает: Проверяет is_empty() для нового кэша.
        Цель: Убедиться, что новый кэш считается пустым.
        """
        print("Настройка: Создание нового кэша...")
        cache = ModelInfoCache()
        
        print("Проверка: is_empty() возвращает True...")
        print(f"Сравниваем is_empty(): Ожидалось True, Получено {cache.is_empty()}")
        assert cache.is_empty() is True
    
    @pytest.mark.asyncio
    async def test_is_empty_returns_false_after_update(self, sample_models_data):
        """
        Что он делает: Проверяет is_empty() после заполнения.
        Цель: Убедиться, что заполненный кэш не считается пустым.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Проверка: is_empty() возвращает False...")
        print(f"Сравниваем is_empty(): Ожидалось False, Получено {cache.is_empty()}")
        assert cache.is_empty() is False


class TestModelInfoCacheIsStale:
    """Тесты проверки устаревания кэша."""
    
    def test_is_stale_returns_true_for_new_cache(self):
        """
        Что он делает: Проверяет is_stale() для нового кэша.
        Цель: Убедиться, что кэш без обновлений считается устаревшим.
        """
        print("Настройка: Создание нового кэша...")
        cache = ModelInfoCache()
        
        print("Проверка: is_stale() возвращает True...")
        print(f"Сравниваем is_stale(): Ожидалось True, Получено {cache.is_stale()}")
        assert cache.is_stale() is True
    
    @pytest.mark.asyncio
    async def test_is_stale_returns_false_after_recent_update(self, sample_models_data):
        """
        Что он делает: Проверяет is_stale() сразу после обновления.
        Цель: Убедиться, что свежий кэш не считается устаревшим.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Проверка: is_stale() возвращает False...")
        print(f"Сравниваем is_stale(): Ожидалось False, Получено {cache.is_stale()}")
        assert cache.is_stale() is False
    
    @pytest.mark.asyncio
    async def test_is_stale_returns_true_after_ttl_expires(self, sample_models_data):
        """
        Что он делает: Проверяет is_stale() после истечения TTL.
        Цель: Убедиться, что кэш считается устаревшим после TTL.
        """
        print("Настройка: Создание кэша с TTL=0.1 секунды...")
        cache = ModelInfoCache(cache_ttl=0.1)
        await cache.update(sample_models_data)
        
        print("Действие: Ожидание истечения TTL...")
        await asyncio.sleep(0.2)
        
        print("Проверка: is_stale() возвращает True...")
        print(f"Сравниваем is_stale(): Ожидалось True, Получено {cache.is_stale()}")
        assert cache.is_stale() is True


class TestModelInfoCacheGetAllModelIds:
    """Тесты получения списка ID моделей."""
    
    def test_get_all_model_ids_returns_empty_for_new_cache(self):
        """
        Что он делает: Проверяет get_all_model_ids() для пустого кэша.
        Цель: Убедиться, что возвращается пустой список.
        """
        print("Настройка: Создание пустого кэша...")
        cache = ModelInfoCache()
        
        print("Действие: Получение списка ID моделей...")
        model_ids = cache.get_all_model_ids()
        
        print("Проверка: Список пуст...")
        print(f"Сравниваем model_ids: Ожидалось [], Получено {model_ids}")
        assert model_ids == []
    
    @pytest.mark.asyncio
    async def test_get_all_model_ids_returns_all_ids(self, sample_models_data):
        """
        Что он делает: Проверяет get_all_model_ids() для заполненного кэша.
        Цель: Убедиться, что возвращаются все ID моделей.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: Получение списка ID моделей...")
        model_ids = cache.get_all_model_ids()
        
        print("Проверка: Все ID присутствуют...")
        expected_ids = [m["modelId"] for m in sample_models_data]
        print(f"Сравниваем model_ids: Ожидалось {expected_ids}, Получено {model_ids}")
        assert set(model_ids) == set(expected_ids)


class TestModelInfoCacheThreadSafety:
    """Тесты потокобезопасности кэша."""
    
    @pytest.mark.asyncio
    async def test_concurrent_updates_dont_corrupt_cache(self, sample_models_data):
        """
        Что он делает: Проверяет потокобезопасность при параллельных update.
        Цель: Убедиться, что asyncio.Lock защищает от race conditions.
        """
        print("Настройка: Создание кэша...")
        cache = ModelInfoCache()
        
        async def update_with_data(data):
            await cache.update(data)
        
        print("Действие: 10 параллельных обновлений...")
        tasks = []
        for i in range(10):
            data = [{"modelId": f"model-{i}", "tokenLimits": {"maxInputTokens": 100000 + i}}]
            tasks.append(update_with_data(data))
        
        await asyncio.gather(*tasks)
        
        print("Проверка: Кэш содержит данные последнего обновления...")
        # Из-за race condition, мы не знаем какое обновление было последним,
        # но кэш должен содержать ровно одну модель
        print(f"Сравниваем size: Ожидалось 1, Получено {cache.size}")
        assert cache.size == 1
        
        print("Проверка: Кэш не повреждён...")
        model_ids = cache.get_all_model_ids()
        assert len(model_ids) == 1
        assert model_ids[0].startswith("model-")
    
    @pytest.mark.asyncio
    async def test_concurrent_reads_are_safe(self, sample_models_data):
        """
        Что он делает: Проверяет безопасность параллельных чтений.
        Цель: Убедиться, что множественные get() не вызывают проблем.
        """
        print("Настройка: Создание и заполнение кэша...")
        cache = ModelInfoCache()
        await cache.update(sample_models_data)
        
        print("Действие: 100 параллельных чтений...")
        async def read_model():
            return cache.get("claude-sonnet-4")
        
        results = await asyncio.gather(*[read_model() for _ in range(100)])
        
        print("Проверка: Все чтения вернули одинаковый результат...")
        assert all(r is not None for r in results)
        assert all(r["modelId"] == "claude-sonnet-4" for r in results)