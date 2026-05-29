# Provider 目录

> 坐山客已知的 AI Provider 和模型列表。
> 覆盖市面上所有主流 AI 模型提供商。
> 每日自动检查更新。
>
> 最后更新: 2026-05-29

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

### deepseek-reasoner
- display_name: DeepSeek Reasoner (R1)
- temperature: 0.5
- max_tokens: 65536
- context_length: 131072
- repeat_penalty: 1.05
- vision: false
- function_calling: false

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

### gpt-4.1
- display_name: GPT-4.1
- temperature: 0.7
- max_tokens: 32768
- context_length: 1047576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-4.1-mini
- display_name: GPT-4.1 Mini
- temperature: 0.7
- max_tokens: 32768
- context_length: 1047576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-4.1-nano
- display_name: GPT-4.1 Nano
- temperature: 0.7
- max_tokens: 32768
- context_length: 1047576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-5
- display_name: GPT-5
- temperature: 0.7
- max_tokens: 128000
- context_length: 272000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-5-mini
- display_name: GPT-5 Mini
- temperature: 0.7
- max_tokens: 128000
- context_length: 272000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gpt-5-pro
- display_name: GPT-5 Pro
- temperature: 0.7
- max_tokens: 272000
- context_length: 272000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### o1
- display_name: o1
- temperature: 1.0
- max_tokens: 100000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### o3
- display_name: o3
- temperature: 1.0
- max_tokens: 100000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### o3-pro
- display_name: o3 Pro
- temperature: 1.0
- max_tokens: 100000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
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

### claude-opus-4
- display_name: Claude Opus 4
- temperature: 0.7
- max_tokens: 32000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-sonnet-4-5
- display_name: Claude Sonnet 4.5
- temperature: 0.7
- max_tokens: 64000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-haiku-4-5
- display_name: Claude Haiku 4.5
- temperature: 0.7
- max_tokens: 64000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-sonnet-4-6
- display_name: Claude Sonnet 4.6
- temperature: 0.7
- max_tokens: 64000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-opus-4-5
- display_name: Claude Opus 4.5
- temperature: 0.7
- max_tokens: 32000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-opus-4-6
- display_name: Claude Opus 4.6
- temperature: 0.7
- max_tokens: 64000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-opus-4-7
- display_name: Claude Opus 4.7
- temperature: 0.7
- max_tokens: 64000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### claude-opus-4-8
- display_name: Claude Opus 4.8
- temperature: 0.7
- max_tokens: 64000
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

### gemini-2.5-flash-lite
- display_name: Gemini 2.5 Flash Lite
- temperature: 0.7
- max_tokens: 65535
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gemini-3-flash-preview
- display_name: Gemini 3 Flash (Preview)
- temperature: 0.7
- max_tokens: 65535
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gemini-3.5-flash
- display_name: Gemini 3.5 Flash
- temperature: 0.7
- max_tokens: 65535
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### gemini-3.1-pro-preview
- display_name: Gemini 3.1 Pro (Preview)
- temperature: 0.7
- max_tokens: 65535
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

### grok-4
- display_name: Grok 4
- temperature: 0.7
- max_tokens: 256000
- context_length: 256000
- repeat_penalty: 1.05
- vision: true
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

### mistral-large-2411
- display_name: Mistral Large 2411
- temperature: 0.7
- max_tokens: 128000
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mistral-small-3.2
- display_name: Mistral Small 3.2
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
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

### qwen3-max
- display_name: Qwen3 Max
- temperature: 0.7
- max_tokens: 65536
- context_length: 258048
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen3.5-plus
- display_name: Qwen3.5 Plus
- temperature: 0.7
- max_tokens: 65536
- context_length: 991808
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen3-coder-plus
- display_name: Qwen3 Coder Plus
- temperature: 0.7
- max_tokens: 65536
- context_length: 997952
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen3-vl-plus
- display_name: Qwen3 VL Plus (视觉)
- temperature: 0.7
- max_tokens: 32768
- context_length: 260096
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen3.6-plus
- display_name: Qwen3.6 Plus
- temperature: 0.7
- max_tokens: 65536
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### qwen3.6-max
- display_name: Qwen3.6 Max
- temperature: 0.7
- max_tokens: 65536
- context_length: 262144
- repeat_penalty: 1.05
- vision: true
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

### doubao-seed-2-0-pro
- display_name: 豆包 Seed 2.0 Pro
- temperature: 0.7
- max_tokens: 128000
- context_length: 256000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### doubao-seed-2-0-lite
- display_name: 豆包 Seed 2.0 Lite
- temperature: 0.7
- max_tokens: 128000
- context_length: 256000
- repeat_penalty: 1.05
- vision: true
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

### glm-4.5
- display_name: GLM-4.5
- temperature: 0.7
- max_tokens: 32000
- context_length: 128000
- repeat_penalty: 1.05
- vision: false
- function_calling: true

### glm-4.5v
- display_name: GLM-4.5V (视觉)
- temperature: 0.7
- max_tokens: 32000
- context_length: 128000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-4.6
- display_name: GLM-4.6
- temperature: 0.7
- max_tokens: 128000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-4.7
- display_name: GLM-4.7
- temperature: 0.7
- max_tokens: 128000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-5
- display_name: GLM-5
- temperature: 0.7
- max_tokens: 128000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### glm-5-1
- display_name: GLM-5.1
- temperature: 0.7
- max_tokens: 128000
- context_length: 200000
- repeat_penalty: 1.05
- vision: true
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

### kimi-k2-instruct
- display_name: Kimi K2 Instruct
- temperature: 0.7
- max_tokens: 131072
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### kimi-k2-thinking
- display_name: Kimi K2 Thinking
- temperature: 0.7
- max_tokens: 131072
- context_length: 262144
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### kimi-k2.5
- display_name: Kimi K2.5
- temperature: 0.7
- max_tokens: 262144
- context_length: 262144
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### kimi-k2-6
- display_name: Kimi K2.6
- temperature: 0.7
- max_tokens: 262144
- context_length: 262144
- repeat_penalty: 1.05
- vision: true
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

### step-3-5-flash
- display_name: Step 3.5 Flash
- temperature: 0.7
- max_tokens: 32768
- context_length: 131072
- repeat_penalty: 1.05
- vision: true
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

### mimo-v2.5
- display_name: MiMo v2.5
- temperature: 0.7
- max_tokens: 131072
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true

### mimo-v2.5-pro
- display_name: MiMo v2.5 Pro
- temperature: 0.7
- max_tokens: 16384
- context_length: 1048576
- repeat_penalty: 1.05
- vision: true
- function_calling: true
