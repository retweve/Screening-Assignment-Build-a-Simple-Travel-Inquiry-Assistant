# WanderFlow Travel Inquiry Assistant

A lightweight Python prototype that accepts raw customer travel inquiry messages and returns structured JSON — including extracted trip details and a short, professional AI-generated reply.

---

## Features

- Extracts or infers key fields: `destination`, `trip_type`, `duration`, `travel_time`, `group_size`, `budget`, `intent`, `missing_fields`
- Generates a short, context-aware customer reply (`initial_response` or `clarifying_question`)
- Uses an AI API (OpenAI or compatible) for high-quality extraction and reply generation
- Falls back gracefully to rule-based heuristics when no API key is configured
- Input validation, structured logging, and unit tests included

---

## Quick Start

### 1. Clone and install dependencies

```bash
git clone https://github.com/retweve/Screening-Assignment-Build-a-Simple-Travel-Inquiry-Assistant
cd Screening-Assignment-Build-a-Simple-Travel-Inquiry-Assistant
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy `.env.example` to `.env` and fill in your API key:

```bash
cp .env.example .env
# then edit .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `OPENAI_API_KEY` | No* | _(empty)_ | API key for OpenAI or compatible provider |
| `OPENAI_API_BASE` | No | `https://api.openai.com/v1/chat/completions` | Override for Azure OpenAI or other providers |
| `AI_MODEL` | No | `gpt-4o-mini` | Model name to use |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity |

> \* If `OPENAI_API_KEY` is not set, the system falls back to rule-based extraction automatically.

### 3. Run the API server

```bash
uvicorn app:app --reload
```

The server starts at `http://127.0.0.1:8000`.

---

## API Usage

### `POST /inquire`

**Request**

```json
{
  "message": "Hi, I want to plan a 7-day trip to Japan in October for 2 people. Budget is around 3000 USD."
}
```

**Response**

```json
{
  "destination": "Japan",
  "trip_type": "general leisure",
  "duration": "7 days",
  "travel_time": "October",
  "group_size": 2,
  "budget": 3000,
  "intent": "trip planning",
  "missing_fields": [],
  "reply_type": "initial_response",
  "reply": "Thanks for your message! We received your inquiry about a trip to Japan, for 7 days, in October, for 2 people, with a budget of around $3,000 USD. We'd love to help you plan the perfect trip and will follow up with suitable options."
}
```

### Interactive docs

Browse and test all endpoints at `http://127.0.0.1:8000/docs` (Swagger UI).

---

## Sample Inquiries and Outputs

All 8 sample messages from the assignment are handled:

| # | Message | Expected Behaviour |
|---|---|---|
| 1 | "Hi, I want to plan a 7-day trip to Japan in October for 2 people. Budget is around 3000 USD." | Full extraction → `initial_response` |
| 2 | "Do you have family-friendly tours in Europe?" | Family/Europe detected, time/budget missing → `clarifying_question` |
| 3 | "I saw your post online. Can you help me plan a honeymoon trip?" | Honeymoon trip type → `clarifying_question` (most fields missing) |
| 4 | "Need visa help for a trip to Canada." | Visa intent + Canada → `clarifying_question` |
| 5 | "What's the price?" | Pricing inquiry, minimal info → `clarifying_question` |
| 6 | "I want to travel next month but I don't know where to go." | Destination unknown → `clarifying_question` |
| 7 | "Looking for a cheap beach vacation." | Beach trip type, budget implicit → `clarifying_question` |
| 8 | "Can someone contact me? I am ready to book." | Booking intent → `clarifying_question` (details missing) |

---

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

本机验证：Python 3.14.3 下 **36 passed**（fastapi 0.135.3 / httpx 0.28.1 / pydantic 2.12.5 / python-dotenv）。注意：`requirements.txt` 目前是下限约束、没有锁文件，安装结果可能随时间变化（依赖可复现性待补）。

---

## Project Structure

```
Screening-Assignment-Build-a-Simple-Travel-Inquiry-Assistant/
├── app.py              # FastAPI application and route definitions
├── parser.py           # Field extraction (AI + rule-based) and reply generation
├── config.py           # Environment-variable configuration
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
├── README.md           # This file
└── tests/
    └── test_parser.py  # Unit tests for parser logic
```

---

## Design Choices

### AI-first, rule-based fallback

The system tries the AI API first for the richest extraction and most natural reply. If the API key is absent or the call fails, it falls back to a set of regex-based heuristics and a template-driven reply builder. This means the prototype works out of the box without any API key, while producing better results when one is configured.

### Consistency requirement

The reply is generated **from the extracted structured fields**, not directly from the raw message. This ensures the reply accurately reflects what was understood, avoiding hallucinated details.

### Missing-field logic

Fields are classified as "important" (`destination`, `travel_time`, `group_size`, `budget`). If more than one is missing the system returns a `clarifying_question` reply that asks for the single most critical missing piece in a natural way.

### Minimal scope

The prototype deliberately avoids over-engineering. There is no database, no authentication, and no session state — just a clean stateless request/response cycle appropriate for a screening task.

---

## Assumptions and Limitations

- Budget is assumed to be in USD. Multi-currency detection is not implemented.
- Destination extraction in rule-based mode relies on a curated list of common travel destinations. Less common locations may not be detected without the AI API.
- The AI API is expected to return valid JSON. The system strips markdown code fences if present and falls back on parse errors.
- No rate limiting or authentication is applied to the API endpoint (out of scope for this prototype).

---

## License

MIT，见 [LICENSE](LICENSE)。
