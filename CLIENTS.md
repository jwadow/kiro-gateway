# Connecting Clients to Kiro Gateway

## OpenCode

Add a provider to your `opencode.json` (or `~/.config/opencode/config.json`):

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "kiro": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Kiro Gateway",
      "options": {
        "baseURL": "http://localhost:8000/v1"
      },
      "models": {
        "claude-opus-4.6": {
          "name": "Claude Opus 4.6 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        },
        "claude-sonnet-4.6": {
          "name": "Claude Sonnet 4.6 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        },
        "claude-opus-4.5": {
          "name": "Claude Opus 4.5 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        },
        "claude-sonnet-4.5": {
          "name": "Claude Sonnet 4.5 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        },
        "claude-sonnet-4": {
          "name": "Claude Sonnet 4 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        },
        "claude-haiku-4.5": {
          "name": "Claude Haiku 4.5 (Kiro)",
          "modalities": {
            "input": ["text", "image"],
            "output": ["text"]
          }
        }
      }
    }
  }
}
```

Then export the env var (or add to your shell profile):

```bash
export KIRO_API_KEY="<same value as PROXY_API_KEY>"
```

The env var name is derived from the provider ID (`kiro`) uppercased + `_API_KEY`.

Alternatively, run `/connect` inside OpenCode, search for your custom `kiro` provider, and paste your `PROXY_API_KEY` value when prompted.

Launch OpenCode and pick the Kiro model from the model selector (`/models`).

---

## VS Code

You can use Kiro Gateway as a custom language model in VS Code Copilot Chat (requires VS Code Insiders with Custom Endpoint support).

1. Open the Command Palette and run **Chat: Manage Language Models**
2. Select **Add Models** → **Custom Endpoint**
3. Enter a group name (e.g. "Kiro Gateway"), your `PROXY_API_KEY`, and select **Chat Completions** as the API type
4. Configure the `chatLanguageModels.json` file that opens:

```json
[
  {
    "name": "Kiro Gateway",
    "vendor": "customendpoint",
    "apiKey": "pick-any-secret-string",
    "apiType": "chat-completions",
    "models": [
      {
        "id": "claude-opus-4.6",
        "name": "Claude Opus 4.6 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 200000,
        "maxOutputTokens": 64000
      },
      {
        "id": "claude-sonnet-4.6",
        "name": "Claude Sonnet 4.6 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 1000000,
        "maxOutputTokens": 64000
      },
      {
        "id": "claude-opus-4.5",
        "name": "Claude Opus 4.5 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 200000,
        "maxOutputTokens": 64000
      },
      {
        "id": "claude-sonnet-4.5",
        "name": "Claude Sonnet 4.5 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 200000,
        "maxOutputTokens": 64000
      },
      {
        "id": "claude-sonnet-4",
        "name": "Claude Sonnet 4 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 200000,
        "maxOutputTokens": 64000
      },
      {
        "id": "claude-haiku-4.5",
        "name": "Claude Haiku 4.5 (Kiro)",
        "url": "http://localhost:8000/v1/chat/completions",
        "toolCalling": true,
        "vision": true,
        "maxInputTokens": 200000,
        "maxOutputTokens": 64000
      }
    ]
  }
]
```

Replace `apiKey` with your actual `PROXY_API_KEY`. Add or remove models based on what's available on your Kiro tier (check `make health` output or the `/v1/models` endpoint).

After saving, select the model from the model picker in VS Code chat.
