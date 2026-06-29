import json

from trading_lab.local_worker import LocalAIWorker


class FakeHTTPClient:
    def __init__(self):
        self.payloads = []

    def post_json(self, url, payload, timeout):
        self.payloads.append((url, payload, timeout))
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(
                            {
                                "approved": True,
                                "thesis": "setup matches prior successful examples",
                                "risk_officer_objection": "watch spread",
                            }
                        )
                    }
                }
            ]
        }


def test_local_ai_worker_uses_openai_compatible_chat_and_parses_json():
    client = FakeHTTPClient()
    worker = LocalAIWorker(base_url="http://local:8097/v1", model="qwen-local", http_client=client)

    result = worker.review({"ticker": "AAPL", "strategy_id": "opening-range-breakout"})

    assert result["approved"] is True
    assert result["model_used"] == "qwen-local"
    assert client.payloads[0][0] == "http://local:8097/v1/chat/completions"
    assert client.payloads[0][1]["model"] == "qwen-local"
    assert client.payloads[0][1]["temperature"] == 0.2


def test_local_ai_worker_includes_training_examples_when_available():
    class Memory:
        def relevant_examples(self, *, symbol, strategy_id, limit):
            return [{"symbol": symbol, "strategy_used": strategy_id, "lesson_label": "hold_filter"}]

    client = FakeHTTPClient()
    worker = LocalAIWorker(base_url="http://local:8097/v1", model="qwen-local", http_client=client, training_memory=Memory())

    worker.review({"ticker": "AAPL", "strategy_id": "opening-range-breakout"})

    user_content = client.payloads[0][1]["messages"][1]["content"]
    assert "training_examples" in user_content
    assert "hold_filter" in user_content


def test_local_ai_worker_fails_closed_on_bad_json():
    class BadClient:
        def post_json(self, url, payload, timeout):
            return {"choices": [{"message": {"content": "not json"}}]}

    worker = LocalAIWorker(base_url="http://local:8097/v1", model="qwen-local", http_client=BadClient())

    result = worker.review({"ticker": "AAPL"})

    assert result["approved"] is False
    assert "invalid_json" in result["risk_officer_objection"]
