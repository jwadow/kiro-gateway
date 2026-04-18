# -*- coding: utf-8 -*-

"""
Unit tests for OpenAI Pydantic models.

Comprehensive tests for all OpenAI-compatible API models:
- Model listing (OpenAIModel, ModelList)
- Chat messages (ChatMessage)
- Tools (ToolFunction, Tool)
- Requests (ChatCompletionRequest)
- Responses (ChatCompletionChoice, ChatCompletionUsage, ChatCompletionResponse)
- Streaming (ChatCompletionChunk, ChatCompletionChunkChoice, ChatCompletionChunkDelta)
"""

import pytest
from pydantic import ValidationError

from kiro.models_openai import (
    # Model listing
    OpenAIModel,
    ModelList,
    # Chat messages
    ChatMessage,
    # Tools
    ToolFunction,
    Tool,
    # Requests
    ChatCompletionRequest,
    # Responses
    ChatCompletionChoice,
    ChatCompletionUsage,
    ChatCompletionResponse,
    # Streaming
    ChatCompletionChunkDelta,
    ChatCompletionChunkChoice,
    ChatCompletionChunk,
)


# ==================================================================================================
# Tests for OpenAIModel
# ==================================================================================================

class TestOpenAIModel:
    """Tests for OpenAIModel Pydantic model."""
    
    def test_valid_model(self):
        """
        What it does: Verifies creation of valid OpenAIModel.
        Purpose: Ensure model accepts valid data.
        """
        print("Setup: Creating OpenAIModel with valid data...")
        model = OpenAIModel(
            id="claude-sonnet-4-5",
            description="Claude Sonnet 4.5 model"
        )
        
        print(f"Result: {model}")
        print(f"Comparing id: Expected 'claude-sonnet-4-5', Got '{model.id}'")
        assert model.id == "claude-sonnet-4-5"
        
        print(f"Comparing object: Expected 'model', Got '{model.object}'")
        assert model.object == "model"
        
        print(f"Comparing owned_by: Expected 'anthropic', Got '{model.owned_by}'")
        assert model.owned_by == "anthropic"
        
        print(f"Comparing description: Got '{model.description}'")
        assert model.description == "Claude Sonnet 4.5 model"
    
    def test_requires_id(self):
        """
        What it does: Verifies that id is required.
        Purpose: Ensure validation fails without id.
        """
        print("Setup: Attempting to create OpenAIModel without id...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            OpenAIModel()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "id" in str(exc_info.value)
    
    def test_object_defaults_to_model(self):
        """
        What it does: Verifies that object defaults to "model".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating OpenAIModel without explicit object...")
        model = OpenAIModel(id="test-model")
        
        print(f"Comparing object: Expected 'model', Got '{model.object}'")
        assert model.object == "model"
    
    def test_owned_by_defaults_to_anthropic(self):
        """
        What it does: Verifies that owned_by defaults to "anthropic".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating OpenAIModel without explicit owned_by...")
        model = OpenAIModel(id="test-model")
        
        print(f"Comparing owned_by: Expected 'anthropic', Got '{model.owned_by}'")
        assert model.owned_by == "anthropic"
    
    def test_created_is_auto_generated(self):
        """
        What it does: Verifies that created timestamp is auto-generated.
        Purpose: Ensure timestamp is set automatically.
        """
        print("Setup: Creating OpenAIModel without explicit created...")
        model = OpenAIModel(id="test-model")
        
        print(f"Comparing created: Got {model.created}")
        assert model.created > 0
        assert isinstance(model.created, int)
    
    def test_description_is_optional(self):
        """
        What it does: Verifies that description is optional.
        Purpose: Ensure models without description work.
        """
        print("Setup: Creating OpenAIModel without description...")
        model = OpenAIModel(id="test-model")
        
        print(f"Comparing description: Expected None, Got {model.description}")
        assert model.description is None


# ==================================================================================================
# Tests for ModelList
# ==================================================================================================

class TestModelList:
    """Tests for ModelList Pydantic model."""
    
    def test_valid_model_list(self):
        """
        What it does: Verifies creation of valid ModelList.
        Purpose: Ensure model list accepts valid data.
        """
        print("Setup: Creating ModelList with valid data...")
        model_list = ModelList(
            data=[
                OpenAIModel(id="claude-sonnet-4-5"),
                OpenAIModel(id="claude-opus-4")
            ]
        )
        
        print(f"Result: {model_list}")
        print(f"Comparing object: Expected 'list', Got '{model_list.object}'")
        assert model_list.object == "list"
        
        print(f"Comparing data length: Expected 2, Got {len(model_list.data)}")
        assert len(model_list.data) == 2
    
    def test_object_defaults_to_list(self):
        """
        What it does: Verifies that object defaults to "list".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ModelList without explicit object...")
        model_list = ModelList(data=[])
        
        print(f"Comparing object: Expected 'list', Got '{model_list.object}'")
        assert model_list.object == "list"
    
    def test_requires_data(self):
        """
        What it does: Verifies that data is required.
        Purpose: Ensure validation fails without data.
        """
        print("Setup: Attempting to create ModelList without data...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ModelList()
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "data" in str(exc_info.value)
    
    def test_accepts_empty_list(self):
        """
        What it does: Verifies that empty list is accepted.
        Purpose: Ensure empty model list works.
        """
        print("Setup: Creating ModelList with empty data...")
        model_list = ModelList(data=[])
        
        print(f"Comparing data: Expected [], Got {model_list.data}")
        assert model_list.data == []


# ==================================================================================================
# Tests for ChatMessage
# ==================================================================================================

class TestChatMessage:
    """Tests for ChatMessage Pydantic model."""
    
    def test_valid_user_message(self):
        """
        What it does: Verifies creation of valid user message.
        Purpose: Ensure model accepts valid user message.
        """
        print("Setup: Creating ChatMessage with user role...")
        message = ChatMessage(role="user", content="Hello!")
        
        print(f"Result: {message}")
        print(f"Comparing role: Expected 'user', Got '{message.role}'")
        assert message.role == "user"
        
        print(f"Comparing content: Expected 'Hello!', Got '{message.content}'")
        assert message.content == "Hello!"
    
    def test_valid_assistant_message(self):
        """
        What it does: Verifies creation of valid assistant message.
        Purpose: Ensure model accepts valid assistant message.
        """
        print("Setup: Creating ChatMessage with assistant role...")
        message = ChatMessage(role="assistant", content="Hi there!")
        
        print(f"Result: {message}")
        print(f"Comparing role: Expected 'assistant', Got '{message.role}'")
        assert message.role == "assistant"
    
    def test_valid_system_message(self):
        """
        What it does: Verifies creation of valid system message.
        Purpose: Ensure model accepts valid system message.
        """
        print("Setup: Creating ChatMessage with system role...")
        message = ChatMessage(role="system", content="You are helpful.")
        
        print(f"Result: {message}")
        print(f"Comparing role: Expected 'system', Got '{message.role}'")
        assert message.role == "system"
    
    def test_valid_tool_message(self):
        """
        What it does: Verifies creation of valid tool message.
        Purpose: Ensure model accepts valid tool message.
        """
        print("Setup: Creating ChatMessage with tool role...")
        message = ChatMessage(
            role="tool",
            content="Tool result",
            tool_call_id="call_123"
        )
        
        print(f"Result: {message}")
        print(f"Comparing role: Expected 'tool', Got '{message.role}'")
        assert message.role == "tool"
        
        print(f"Comparing tool_call_id: Expected 'call_123', Got '{message.tool_call_id}'")
        assert message.tool_call_id == "call_123"
    
    def test_requires_role(self):
        """
        What it does: Verifies that role is required.
        Purpose: Ensure validation fails without role.
        """
        print("Setup: Attempting to create ChatMessage without role...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatMessage(content="Hello")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "role" in str(exc_info.value)
    
    def test_content_is_optional(self):
        """
        What it does: Verifies that content is optional.
        Purpose: Ensure messages without content work (e.g., tool calls).
        """
        print("Setup: Creating ChatMessage without content...")
        message = ChatMessage(role="assistant")
        
        print(f"Comparing content: Expected None, Got {message.content}")
        assert message.content is None
    
    def test_accepts_list_content(self):
        """
        What it does: Verifies that list content is accepted.
        Purpose: Ensure multimodal content works.
        """
        print("Setup: Creating ChatMessage with list content...")
        message = ChatMessage(
            role="user",
            content=[
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": "https://example.com/img.jpg"}}
            ]
        )
        
        print(f"Result: {message}")
        print(f"Comparing content type: Expected list, Got {type(message.content)}")
        assert isinstance(message.content, list)
        assert len(message.content) == 2
    
    def test_accepts_tool_calls(self):
        """
        What it does: Verifies that tool_calls is accepted.
        Purpose: Ensure assistant messages with tool calls work.
        """
        print("Setup: Creating ChatMessage with tool_calls...")
        message = ChatMessage(
            role="assistant",
            content="I'll call a tool",
            tool_calls=[{
                "id": "call_123",
                "type": "function",
                "function": {"name": "get_weather", "arguments": '{"location": "Moscow"}'}
            }]
        )
        
        print(f"Result: {message}")
        print(f"Comparing tool_calls: Got {message.tool_calls}")
        assert message.tool_calls is not None
        assert len(message.tool_calls) == 1
    
    def test_name_is_optional(self):
        """
        What it does: Verifies that name is optional.
        Purpose: Ensure messages without name work.
        """
        print("Setup: Creating ChatMessage without name...")
        message = ChatMessage(role="user", content="Hello")
        
        print(f"Comparing name: Expected None, Got {message.name}")
        assert message.name is None
    
    def test_accepts_name(self):
        """
        What it does: Verifies that name is accepted.
        Purpose: Ensure named messages work.
        """
        print("Setup: Creating ChatMessage with name...")
        message = ChatMessage(role="user", content="Hello", name="John")
        
        print(f"Comparing name: Expected 'John', Got '{message.name}'")
        assert message.name == "John"
    
    def test_extra_fields_allowed(self):
        """
        What it does: Verifies that extra fields are allowed.
        Purpose: Ensure model_config extra="allow" works.
        """
        print("Setup: Creating ChatMessage with extra field...")
        message = ChatMessage(role="user", content="Hello", custom_field="value")
        
        print(f"Comparing custom_field: Got '{message.custom_field}'")
        assert message.custom_field == "value"


# ==================================================================================================
# Tests for ToolFunction
# ==================================================================================================

class TestToolFunction:
    """Tests for ToolFunction Pydantic model."""
    
    def test_valid_tool_function(self):
        """
        What it does: Verifies creation of valid ToolFunction.
        Purpose: Ensure model accepts valid tool function.
        """
        print("Setup: Creating ToolFunction with valid data...")
        func = ToolFunction(
            name="get_weather",
            description="Get weather for a location",
            parameters={
                "type": "object",
                "properties": {"location": {"type": "string"}}
            }
        )
        
        print(f"Result: {func}")
        print(f"Comparing name: Expected 'get_weather', Got '{func.name}'")
        assert func.name == "get_weather"
        
        print(f"Comparing description: Got '{func.description}'")
        assert func.description == "Get weather for a location"
        
        print(f"Comparing parameters: Got {func.parameters}")
        assert "properties" in func.parameters
    
    def test_requires_name(self):
        """
        What it does: Verifies that name is required.
        Purpose: Ensure validation fails without name.
        """
        print("Setup: Attempting to create ToolFunction without name...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ToolFunction(description="Test")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "name" in str(exc_info.value)
    
    def test_description_is_optional(self):
        """
        What it does: Verifies that description is optional.
        Purpose: Ensure functions without description work.
        """
        print("Setup: Creating ToolFunction without description...")
        func = ToolFunction(name="test_func")
        
        print(f"Comparing description: Expected None, Got {func.description}")
        assert func.description is None
    
    def test_parameters_is_optional(self):
        """
        What it does: Verifies that parameters is optional.
        Purpose: Ensure functions without parameters work.
        """
        print("Setup: Creating ToolFunction without parameters...")
        func = ToolFunction(name="no_params_func")
        
        print(f"Comparing parameters: Expected None, Got {func.parameters}")
        assert func.parameters is None


# ==================================================================================================
# Tests for Tool
# ==================================================================================================

class TestTool:
    """Tests for Tool Pydantic model."""
    
    def test_valid_tool(self):
        """
        What it does: Verifies creation of valid Tool.
        Purpose: Ensure model accepts valid tool.
        """
        print("Setup: Creating Tool with valid data...")
        tool = Tool(
            type="function",
            function=ToolFunction(
                name="get_weather",
                description="Get weather",
                parameters={}
            )
        )
        
        print(f"Result: {tool}")
        print(f"Comparing type: Expected 'function', Got '{tool.type}'")
        assert tool.type == "function"
        
        print(f"Comparing function.name: Expected 'get_weather', Got '{tool.function.name}'")
        assert tool.function.name == "get_weather"
    
    def test_type_defaults_to_function(self):
        """
        What it does: Verifies that type defaults to "function".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating Tool without explicit type...")
        tool = Tool(function=ToolFunction(name="test"))
        
        print(f"Comparing type: Expected 'function', Got '{tool.type}'")
        assert tool.type == "function"
    
    def test_function_is_optional_for_flat_format(self):
        """
        What it does: Verifies that function is optional (for flat format compatibility).
        Purpose: Ensure flat format (Cursor-style) is supported without function field.
        """
        print("Setup: Creating Tool with flat format (name, description, input_schema)...")
        tool = Tool(
            type="function",
            name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}}
        )
        
        print(f"Result: {tool}")
        print(f"Comparing name: Expected 'test_tool', Got '{tool.name}'")
        assert tool.name == "test_tool"
        
        print(f"Comparing function: Expected None, Got {tool.function}")
        assert tool.function is None
        
        print(f"Comparing description: Expected 'A test tool', Got '{tool.description}'")
        assert tool.description == "A test tool"
    
    def test_standard_format_still_works(self):
        """
        What it does: Verifies that standard OpenAI format still works.
        Purpose: Ensure backward compatibility with standard format.
        """
        print("Setup: Creating Tool with standard OpenAI format (function field)...")
        tool = Tool(
            type="function",
            function=ToolFunction(name="standard_tool", description="Standard")
        )
        
        print(f"Result: {tool}")
        print(f"Comparing function.name: Expected 'standard_tool', Got '{tool.function.name}'")
        assert tool.function.name == "standard_tool"
        
        print(f"Comparing name: Expected None, Got {tool.name}")
        assert tool.name is None


# ==================================================================================================
# Tests for ChatCompletionRequest
# ==================================================================================================

class TestChatCompletionRequest:
    """Tests for ChatCompletionRequest Pydantic model."""
    
    def test_valid_request(self):
        """
        What it does: Verifies creation of valid ChatCompletionRequest.
        Purpose: Ensure model accepts valid request.
        """
        print("Setup: Creating ChatCompletionRequest with valid data...")
        request = ChatCompletionRequest(
            model="claude-sonnet-4-5",
            messages=[ChatMessage(role="user", content="Hello")]
        )
        
        print(f"Result: {request}")
        print(f"Comparing model: Expected 'claude-sonnet-4-5', Got '{request.model}'")
        assert request.model == "claude-sonnet-4-5"
        
        print(f"Comparing messages length: Expected 1, Got {len(request.messages)}")
        assert len(request.messages) == 1
        
        print(f"Comparing stream: Expected False, Got {request.stream}")
        assert request.stream is False
    
    def test_requires_model(self):
        """
        What it does: Verifies that model is required.
        Purpose: Ensure validation fails without model.
        """
        print("Setup: Attempting to create ChatCompletionRequest without model...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionRequest(messages=[ChatMessage(role="user", content="Hi")])
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "model" in str(exc_info.value)
    
    def test_requires_messages(self):
        """
        What it does: Verifies that messages is required.
        Purpose: Ensure validation fails without messages.
        """
        print("Setup: Attempting to create ChatCompletionRequest without messages...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionRequest(model="claude-sonnet-4-5")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "messages" in str(exc_info.value)
    
    def test_requires_at_least_one_message(self):
        """
        What it does: Verifies that at least one message is required.
        Purpose: Ensure validation fails with empty messages.
        """
        print("Setup: Attempting to create ChatCompletionRequest with empty messages...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionRequest(model="claude-sonnet-4-5", messages=[])
        
        print(f"ValidationError raised: {exc_info.value}")
    
    def test_stream_defaults_to_false(self):
        """
        What it does: Verifies that stream defaults to False.
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ChatCompletionRequest without explicit stream...")
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role="user", content="Hi")]
        )
        
        print(f"Comparing stream: Expected False, Got {request.stream}")
        assert request.stream is False
    
    def test_accepts_stream_true(self):
        """
        What it does: Verifies that stream=True is accepted.
        Purpose: Ensure streaming requests work.
        """
        print("Setup: Creating ChatCompletionRequest with stream=True...")
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role="user", content="Hi")],
            stream=True
        )
        
        print(f"Comparing stream: Expected True, Got {request.stream}")
        assert request.stream is True
    
    def test_accepts_tools(self):
        """
        What it does: Verifies that tools are accepted.
        Purpose: Ensure function calling works.
        """
        print("Setup: Creating ChatCompletionRequest with tools...")
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role="user", content="Hi")],
            tools=[Tool(function=ToolFunction(name="test_tool"))]
        )
        
        print(f"Comparing tools: Got {request.tools}")
        assert request.tools is not None
        assert len(request.tools) == 1
    
    def test_accepts_generation_parameters(self):
        """
        What it does: Verifies that generation parameters are accepted.
        Purpose: Ensure temperature, top_p, max_tokens work.
        """
        print("Setup: Creating ChatCompletionRequest with generation params...")
        request = ChatCompletionRequest(
            model="test",
            messages=[ChatMessage(role="user", content="Hi")],
            temperature=0.7,
            top_p=0.9,
            max_tokens=1000
        )
        
        print(f"Comparing temperature: Expected 0.7, Got {request.temperature}")
        assert request.temperature == 0.7
        
        print(f"Comparing top_p: Expected 0.9, Got {request.top_p}")
        assert request.top_p == 0.9
        
        print(f"Comparing max_tokens: Expected 1000, Got {request.max_tokens}")
        assert request.max_tokens == 1000


# ==================================================================================================
# Tests for ChatCompletionUsage
# ==================================================================================================

class TestChatCompletionUsage:
    """Tests for ChatCompletionUsage Pydantic model."""
    
    def test_valid_usage(self):
        """
        What it does: Verifies creation of valid ChatCompletionUsage.
        Purpose: Ensure model accepts valid usage data.
        """
        print("Setup: Creating ChatCompletionUsage with valid data...")
        usage = ChatCompletionUsage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150
        )
        
        print(f"Result: {usage}")
        print(f"Comparing prompt_tokens: Expected 100, Got {usage.prompt_tokens}")
        assert usage.prompt_tokens == 100
        
        print(f"Comparing completion_tokens: Expected 50, Got {usage.completion_tokens}")
        assert usage.completion_tokens == 50
        
        print(f"Comparing total_tokens: Expected 150, Got {usage.total_tokens}")
        assert usage.total_tokens == 150
    
    def test_defaults_to_zero(self):
        """
        What it does: Verifies that all fields default to 0.
        Purpose: Ensure default values are set correctly.
        """
        print("Setup: Creating ChatCompletionUsage without explicit values...")
        usage = ChatCompletionUsage()
        
        print(f"Comparing prompt_tokens: Expected 0, Got {usage.prompt_tokens}")
        assert usage.prompt_tokens == 0
        
        print(f"Comparing completion_tokens: Expected 0, Got {usage.completion_tokens}")
        assert usage.completion_tokens == 0
        
        print(f"Comparing total_tokens: Expected 0, Got {usage.total_tokens}")
        assert usage.total_tokens == 0
    
    def test_credits_used_is_optional(self):
        """
        What it does: Verifies that credits_used is optional.
        Purpose: Ensure Kiro-specific field is optional.
        """
        print("Setup: Creating ChatCompletionUsage without credits_used...")
        usage = ChatCompletionUsage()
        
        print(f"Comparing credits_used: Expected None, Got {usage.credits_used}")
        assert usage.credits_used is None


# ==================================================================================================
# Tests for ChatCompletionChoice
# ==================================================================================================

class TestChatCompletionChoice:
    """Tests for ChatCompletionChoice Pydantic model."""
    
    def test_valid_choice(self):
        """
        What it does: Verifies creation of valid ChatCompletionChoice.
        Purpose: Ensure model accepts valid choice data.
        """
        print("Setup: Creating ChatCompletionChoice with valid data...")
        choice = ChatCompletionChoice(
            index=0,
            message={"role": "assistant", "content": "Hello!"},
            finish_reason="stop"
        )
        
        print(f"Result: {choice}")
        print(f"Comparing index: Expected 0, Got {choice.index}")
        assert choice.index == 0
        
        print(f"Comparing message: Got {choice.message}")
        assert choice.message["role"] == "assistant"
        
        print(f"Comparing finish_reason: Expected 'stop', Got '{choice.finish_reason}'")
        assert choice.finish_reason == "stop"
    
    def test_index_defaults_to_zero(self):
        """
        What it does: Verifies that index defaults to 0.
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ChatCompletionChoice without explicit index...")
        choice = ChatCompletionChoice(message={"role": "assistant", "content": "Hi"})
        
        print(f"Comparing index: Expected 0, Got {choice.index}")
        assert choice.index == 0
    
    def test_requires_message(self):
        """
        What it does: Verifies that message is required.
        Purpose: Ensure validation fails without message.
        """
        print("Setup: Attempting to create ChatCompletionChoice without message...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionChoice(index=0, finish_reason="stop")
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "message" in str(exc_info.value)
    
    def test_finish_reason_is_optional(self):
        """
        What it does: Verifies that finish_reason is optional.
        Purpose: Ensure choices without finish_reason work.
        """
        print("Setup: Creating ChatCompletionChoice without finish_reason...")
        choice = ChatCompletionChoice(message={"role": "assistant", "content": "Hi"})
        
        print(f"Comparing finish_reason: Expected None, Got {choice.finish_reason}")
        assert choice.finish_reason is None


# ==================================================================================================
# Tests for ChatCompletionResponse
# ==================================================================================================

class TestChatCompletionResponse:
    """Tests for ChatCompletionResponse Pydantic model."""
    
    def test_valid_response(self):
        """
        What it does: Verifies creation of valid ChatCompletionResponse.
        Purpose: Ensure model accepts valid response data.
        """
        print("Setup: Creating ChatCompletionResponse with valid data...")
        response = ChatCompletionResponse(
            id="chatcmpl-123",
            model="claude-sonnet-4-5",
            choices=[ChatCompletionChoice(
                message={"role": "assistant", "content": "Hello!"},
                finish_reason="stop"
            )],
            usage=ChatCompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        )
        
        print(f"Result: {response}")
        print(f"Comparing id: Expected 'chatcmpl-123', Got '{response.id}'")
        assert response.id == "chatcmpl-123"
        
        print(f"Comparing object: Expected 'chat.completion', Got '{response.object}'")
        assert response.object == "chat.completion"
        
        print(f"Comparing model: Expected 'claude-sonnet-4-5', Got '{response.model}'")
        assert response.model == "claude-sonnet-4-5"
        
        print(f"Comparing choices length: Expected 1, Got {len(response.choices)}")
        assert len(response.choices) == 1
    
    def test_object_defaults_to_chat_completion(self):
        """
        What it does: Verifies that object defaults to "chat.completion".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ChatCompletionResponse without explicit object...")
        response = ChatCompletionResponse(
            id="test",
            model="test",
            choices=[ChatCompletionChoice(message={"role": "assistant", "content": "Hi"})],
            usage=ChatCompletionUsage()
        )
        
        print(f"Comparing object: Expected 'chat.completion', Got '{response.object}'")
        assert response.object == "chat.completion"
    
    def test_created_is_auto_generated(self):
        """
        What it does: Verifies that created timestamp is auto-generated.
        Purpose: Ensure timestamp is set automatically.
        """
        print("Setup: Creating ChatCompletionResponse without explicit created...")
        response = ChatCompletionResponse(
            id="test",
            model="test",
            choices=[ChatCompletionChoice(message={"role": "assistant", "content": "Hi"})],
            usage=ChatCompletionUsage()
        )
        
        print(f"Comparing created: Got {response.created}")
        assert response.created > 0
        assert isinstance(response.created, int)
    
    def test_requires_id(self):
        """
        What it does: Verifies that id is required.
        Purpose: Ensure validation fails without id.
        """
        print("Setup: Attempting to create ChatCompletionResponse without id...")
        
        print("Action: Creating model (should raise ValidationError)...")
        with pytest.raises(ValidationError) as exc_info:
            ChatCompletionResponse(
                model="test",
                choices=[ChatCompletionChoice(message={"role": "assistant", "content": "Hi"})],
                usage=ChatCompletionUsage()
            )
        
        print(f"ValidationError raised: {exc_info.value}")
        assert "id" in str(exc_info.value)


# ==================================================================================================
# Tests for Streaming Models
# ==================================================================================================

class TestChatCompletionChunkDelta:
    """Tests for ChatCompletionChunkDelta Pydantic model."""
    
    def test_valid_delta_with_content(self):
        """
        What it does: Verifies creation of valid delta with content.
        Purpose: Ensure model accepts content delta.
        """
        print("Setup: Creating ChatCompletionChunkDelta with content...")
        delta = ChatCompletionChunkDelta(content="Hello")
        
        print(f"Result: {delta}")
        print(f"Comparing content: Expected 'Hello', Got '{delta.content}'")
        assert delta.content == "Hello"
    
    def test_valid_delta_with_role(self):
        """
        What it does: Verifies creation of valid delta with role.
        Purpose: Ensure model accepts role delta (first chunk).
        """
        print("Setup: Creating ChatCompletionChunkDelta with role...")
        delta = ChatCompletionChunkDelta(role="assistant")
        
        print(f"Result: {delta}")
        print(f"Comparing role: Expected 'assistant', Got '{delta.role}'")
        assert delta.role == "assistant"
    
    def test_all_fields_optional(self):
        """
        What it does: Verifies that all fields are optional.
        Purpose: Ensure empty delta works.
        """
        print("Setup: Creating empty ChatCompletionChunkDelta...")
        delta = ChatCompletionChunkDelta()
        
        print(f"Comparing role: Expected None, Got {delta.role}")
        assert delta.role is None
        
        print(f"Comparing content: Expected None, Got {delta.content}")
        assert delta.content is None
        
        print(f"Comparing tool_calls: Expected None, Got {delta.tool_calls}")
        assert delta.tool_calls is None
    
    def test_accepts_tool_calls(self):
        """
        What it does: Verifies that tool_calls is accepted.
        Purpose: Ensure streaming tool calls work.
        """
        print("Setup: Creating ChatCompletionChunkDelta with tool_calls...")
        delta = ChatCompletionChunkDelta(
            tool_calls=[{"index": 0, "id": "call_1", "function": {"name": "test"}}]
        )
        
        print(f"Comparing tool_calls: Got {delta.tool_calls}")
        assert delta.tool_calls is not None
        assert len(delta.tool_calls) == 1


class TestChatCompletionChunkChoice:
    """Tests for ChatCompletionChunkChoice Pydantic model."""
    
    def test_valid_chunk_choice(self):
        """
        What it does: Verifies creation of valid chunk choice.
        Purpose: Ensure model accepts valid chunk choice.
        """
        print("Setup: Creating ChatCompletionChunkChoice with valid data...")
        choice = ChatCompletionChunkChoice(
            index=0,
            delta=ChatCompletionChunkDelta(content="Hello")
        )
        
        print(f"Result: {choice}")
        print(f"Comparing index: Expected 0, Got {choice.index}")
        assert choice.index == 0
        
        print(f"Comparing delta.content: Expected 'Hello', Got '{choice.delta.content}'")
        assert choice.delta.content == "Hello"
    
    def test_index_defaults_to_zero(self):
        """
        What it does: Verifies that index defaults to 0.
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ChatCompletionChunkChoice without explicit index...")
        choice = ChatCompletionChunkChoice(delta=ChatCompletionChunkDelta())
        
        print(f"Comparing index: Expected 0, Got {choice.index}")
        assert choice.index == 0
    
    def test_finish_reason_is_optional(self):
        """
        What it does: Verifies that finish_reason is optional.
        Purpose: Ensure intermediate chunks work.
        """
        print("Setup: Creating ChatCompletionChunkChoice without finish_reason...")
        choice = ChatCompletionChunkChoice(delta=ChatCompletionChunkDelta(content="Hi"))
        
        print(f"Comparing finish_reason: Expected None, Got {choice.finish_reason}")
        assert choice.finish_reason is None
    
    def test_accepts_finish_reason(self):
        """
        What it does: Verifies that finish_reason is accepted.
        Purpose: Ensure final chunk works.
        """
        print("Setup: Creating ChatCompletionChunkChoice with finish_reason...")
        choice = ChatCompletionChunkChoice(
            delta=ChatCompletionChunkDelta(),
            finish_reason="stop"
        )
        
        print(f"Comparing finish_reason: Expected 'stop', Got '{choice.finish_reason}'")
        assert choice.finish_reason == "stop"


class TestChatCompletionChunk:
    """Tests for ChatCompletionChunk Pydantic model."""
    
    def test_valid_chunk(self):
        """
        What it does: Verifies creation of valid chunk.
        Purpose: Ensure model accepts valid chunk data.
        """
        print("Setup: Creating ChatCompletionChunk with valid data...")
        chunk = ChatCompletionChunk(
            id="chatcmpl-123",
            model="claude-sonnet-4-5",
            choices=[ChatCompletionChunkChoice(
                delta=ChatCompletionChunkDelta(content="Hello")
            )]
        )
        
        print(f"Result: {chunk}")
        print(f"Comparing id: Expected 'chatcmpl-123', Got '{chunk.id}'")
        assert chunk.id == "chatcmpl-123"
        
        print(f"Comparing object: Expected 'chat.completion.chunk', Got '{chunk.object}'")
        assert chunk.object == "chat.completion.chunk"
        
        print(f"Comparing model: Expected 'claude-sonnet-4-5', Got '{chunk.model}'")
        assert chunk.model == "claude-sonnet-4-5"
    
    def test_object_defaults_to_chunk(self):
        """
        What it does: Verifies that object defaults to "chat.completion.chunk".
        Purpose: Ensure default value is set correctly.
        """
        print("Setup: Creating ChatCompletionChunk without explicit object...")
        chunk = ChatCompletionChunk(
            id="test",
            model="test",
            choices=[ChatCompletionChunkChoice(delta=ChatCompletionChunkDelta())]
        )
        
        print(f"Comparing object: Expected 'chat.completion.chunk', Got '{chunk.object}'")
        assert chunk.object == "chat.completion.chunk"
    
    def test_usage_is_optional(self):
        """
        What it does: Verifies that usage is optional.
        Purpose: Ensure intermediate chunks work without usage.
        """
        print("Setup: Creating ChatCompletionChunk without usage...")
        chunk = ChatCompletionChunk(
            id="test",
            model="test",
            choices=[ChatCompletionChunkChoice(delta=ChatCompletionChunkDelta())]
        )
        
        print(f"Comparing usage: Expected None, Got {chunk.usage}")
        assert chunk.usage is None
    
    def test_accepts_usage(self):
        """
        What it does: Verifies that usage is accepted.
        Purpose: Ensure final chunk with usage works.
        """
        print("Setup: Creating ChatCompletionChunk with usage...")
        chunk = ChatCompletionChunk(
            id="test",
            model="test",
            choices=[ChatCompletionChunkChoice(
                delta=ChatCompletionChunkDelta(),
                finish_reason="stop"
            )],
            usage=ChatCompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        )
        
        print(f"Comparing usage: Got {chunk.usage}")
        assert chunk.usage is not None
        assert chunk.usage.total_tokens == 15


# ==================================================================================================
# Tests for Client Thinking Budget Support (Issue #111)
# ==================================================================================================

class TestReasoningEffort:
    """Tests for reasoning_effort parameter in ChatCompletionRequest."""
    
    def test_reasoning_effort_valid_values(self):
        """
        What it does: Verifies all 6 reasoning_effort values are accepted
        Purpose: Ensure Pydantic validates all official OpenAI reasoning_effort levels
        """
        print("Testing all valid reasoning_effort values...")
        
        for effort in ["none", "minimal", "low", "medium", "high", "xhigh"]:
            print(f"  Testing reasoning_effort='{effort}'...")
            request = ChatCompletionRequest(
                model="claude-sonnet-4.5",
                messages=[ChatMessage(role="user", content="test")],
                reasoning_effort=effort
            )
            
            print(f"  Comparing: expected='{effort}', got='{request.reasoning_effort}'")
            assert request.reasoning_effort == effort
    
    def test_reasoning_effort_optional(self):
        """
        What it does: Verifies reasoning_effort can be None (not specified)
        Purpose: Ensure reasoning_effort is optional parameter
        """
        print("Creating ChatCompletionRequest without reasoning_effort...")
        request = ChatCompletionRequest(
            model="claude-sonnet-4.5",
            messages=[ChatMessage(role="user", content="test")]
        )
        
        print(f"Comparing: expected=None, got={request.reasoning_effort}")
        assert request.reasoning_effort is None
    
    def test_reasoning_effort_invalid_value_rejected(self):
        """
        What it does: Verifies invalid reasoning_effort value is rejected by Pydantic
        Purpose: Ensure type safety for reasoning_effort parameter
        """
        print("Attempting to create ChatCompletionRequest with invalid reasoning_effort...")
        
        from pydantic import ValidationError
        try:
            request = ChatCompletionRequest(
                model="claude-sonnet-4.5",
                messages=[ChatMessage(role="user", content="test")],
                reasoning_effort="ultra"  # Invalid value
            )
            print("ERROR: Should have raised ValidationError!")
            assert False, "Expected ValidationError for invalid reasoning_effort"
        except ValidationError as e:
            print(f"Correctly raised ValidationError: {e}")
            assert "reasoning_effort" in str(e).lower()
