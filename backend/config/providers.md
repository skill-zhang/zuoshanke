# Provider 目录

> 坐山客已知的 AI Provider 和模型列表。
> 覆盖市面上所有主流 AI 模型提供商。
> 每日自动检查更新。
>
> 最后更新: 2026-05-27

## DeepSeek
- display_name: DeepSeek
- base_url: https://api.deepseek.com
- provider_type: openai-compatible

### deepseek-v4-flash
- display_name: DeepSeek v4 Flash
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### deepseek-v4-pro
- display_name: DeepSeek v4 Pro
- temperature: 0.5
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## OpenAI
- display_name: OpenAI
- base_url: https://api.openai.com/v1
- provider_type: openai-compatible

### gpt-4o
- display_name: GPT-4o
- temperature: 0.7
- max_tokens: 16384
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-4o-mini
- display_name: GPT-4o Mini
- temperature: 0.7
- max_tokens: 16384
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### o3-mini
- display_name: o3 Mini
- temperature: 1.0
- max_tokens: 102400
- context_length: 200000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### o4-mini
- display_name: o4 Mini
- temperature: 1.0
- max_tokens: 102400
- context_length: 200000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Anthropic
- display_name: Anthropic
- base_url: https://api.anthropic.com
- provider_type: openai-compatible

### claude-sonnet-4
- display_name: Claude Sonnet 4
- temperature: 0.7
- max_tokens: 8192
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-haiku-3.5
- display_name: Claude Haiku 3.5
- temperature: 0.7
- max_tokens: 8192
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## Google
- display_name: Google Gemini
- base_url: https://generativelanguage.googleapis.com
- provider_type: openai-compatible

### gemini-2.5-pro
- display_name: Gemini 2.5 Pro
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gemini-2.5-flash
- display_name: Gemini 2.5 Flash
- temperature: 0.7
- max_tokens: 8192
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## xAI
- display_name: xAI Grok
- base_url: https://api.x.ai
- provider_type: openai-compatible

### grok-3
- display_name: Grok 3
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### grok-3-mini
- display_name: Grok 3 Mini
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Mistral
- display_name: Mistral AI
- base_url: https://api.mistral.ai
- provider_type: openai-compatible

### mistral-large-3.1
- display_name: Mistral Large 3.1
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mistral-small-3.1
- display_name: Mistral Small 3.1
- temperature: 0.7
- max_tokens: 8192
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Alibaba
- display_name: 通义千问 (Alibaba)
- base_url: https://dashscope.aliyuncs.com/compat-mode/v1
- provider_type: openai-compatible

### qwen-max
- display_name: Qwen Max
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen-plus
- display_name: Qwen Plus
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen-turbo
- display_name: Qwen Turbo
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## ByteDance
- display_name: 豆包 (ByteDance)
- base_url: https://ark.cn-beijing.volces.com/api/v3
- provider_type: openai-compatible

### doubao-pro-32k
- display_name: 豆包 Pro 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### doubao-pro-128k
- display_name: 豆包 Pro 128K
- temperature: 0.7
- max_tokens: 4096
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### doubao-lite-32k
- display_name: 豆包 Lite 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Zhipu
- display_name: 智谱 AI (Zhipu)
- base_url: https://open.bigmodel.cn/api/paas/v4
- provider_type: openai-compatible

### glm-4-plus
- display_name: GLM-4 Plus
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-4-air
- display_name: GLM-4 Air
- temperature: 0.7
- max_tokens: 4096
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Yi
- display_name: 零一万物 Yi
- base_url: https://api.lingyiwanwu.com
- provider_type: openai-compatible

### yi-lightning
- display_name: Yi Lightning
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### yi-vision
- display_name: Yi Vision
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: true
- function_calling: true

## Moonshot
- display_name: 月之暗面 Moonshot
- base_url: https://api.moonshot.cn
- provider_type: openai-compatible

### moonshot-v1-8k
- display_name: Moonshot v1 8K
- temperature: 0.7
- max_tokens: 4096
- context_length: 8192
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### moonshot-v1-32k
- display_name: Moonshot v1 32K
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### moonshot-v1-128k
- display_name: Moonshot v1 128K
- temperature: 0.7
- max_tokens: 4096
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Stepfun
- display_name: 阶跃星辰 Stepfun
- base_url: https://api.stepfun.com
- provider_type: openai-compatible

### step-2-16k
- display_name: Step 2 16K
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### step-1-8k
- display_name: Step 1 8K
- temperature: 0.7
- max_tokens: 4096
- context_length: 8192
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## SiliconFlow
- display_name: SiliconFlow
- base_url: https://api.siliconflow.cn
- provider_type: openai-compatible

### deepseek-ai/DeepSeek-V3
- display_name: DeepSeek V3 (硅基流动)
- temperature: 0.7
- max_tokens: 4096
- context_length: 65536
- repeat_penalty: 1.05
- vision: false
- function_calling: false

### Qwen/Qwen2.5-72B-Instruct
- display_name: Qwen2.5 72B (硅基流动)
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: false
- function_calling: false

## Groq
- display_name: Groq
- base_url: https://api.groq.com/openai
- provider_type: openai-compatible

### llama-3.3-70b-versatile
- display_name: Llama 3.3 70B (Groq)
- temperature: 0.7
- max_tokens: 8192
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### deepseek-r1-distill-llama-70b
- display_name: DeepSeek R1 Distill 70B (Groq)
- temperature: 0.6
- max_tokens: 16384
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: true

## Xiaomi
- display_name: 小米 MiMo
- base_url: https://api.mi.com/ai
- provider_type: openai-compatible

### mimo-pro
- display_name: MiMo Pro
- temperature: 0.7
- max_tokens: 4096
- context_length: 32768
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mimo-lite
- display_name: MiMo Lite
- temperature: 0.7
- max_tokens: 4096
- context_length: 16384
- repeat_penalty: 1.05
- vision: false
- function_calling: true
