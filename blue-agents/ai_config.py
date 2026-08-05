# AI Strategy Configuration
# Adjust these settings to control AI behavior and costs

# Model Selection
# To check available models: https://platform.openai.com/docs/models
# Common options (cheapest to most expensive):
# - gpt-3.5-turbo: Fastest and cheapest (~$0.0005 per 1k tokens)
# - gpt-4o-nano: Ultra-cheap option (check OpenAI docs for exact name & pricing)
# - gpt-4o-mini: Good balance (~$0.15 per 1M input tokens)
# - gpt-4o: Most capable but expensive (~$2.50 per 1M input tokens)
#
# If using nano, you may need to adjust the exact model name below
AI_MODEL = "gpt-4o-mini"  # BEST VALUE: Cheaper than 3.5-turbo + better quality!

# Max tokens for response (lower = cheaper)
# Pokemon strategy typically needs 300-800 tokens
MAX_TOKENS = 800

# Temperature (0.0-1.0)
# Lower = more consistent, Higher = more creative
TEMPERATURE = 0.7

# System prompt
SYSTEM_PROMPT = "You are an expert Pokemon Blue speedrunner and strategist. Provide clear, actionable advice."
