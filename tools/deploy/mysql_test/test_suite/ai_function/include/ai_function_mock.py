#!/usr/bin/env python3

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def embedding_inputs(body):
    values = body.get("input")
    if isinstance(values, str):
        values = [values]
    if not isinstance(values, list) or not values:
        raise ValueError("input must be a nonempty string or array")
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError("input entries must be nonempty strings")
    return values


def vector(dimension):
    if type(dimension) is not int or dimension <= 0:
        raise ValueError("dimensions must be a positive integer")
    return ([0.0, 0.25, 0.5, 0.75] * ((dimension + 3) // 4))[:dimension]


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        return

    def do_POST(self):
        try:
            size = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(size).decode("utf-8"))
            if not isinstance(body, dict):
                raise ValueError("request body must be an object")
            path = self.path.rstrip("/")
            if path.endswith("/compatible-mode/v1/chat/completions"):
                messages = body.get("messages")
                if not isinstance(messages, list) or not messages:
                    raise ValueError("messages must be a nonempty array")
                if "temperature" in body and body["temperature"] != 0.2:
                    raise ValueError("temperature was not forwarded")
                if "max_tokens" in body and (
                    type(body["max_tokens"]) is not int or body["max_tokens"] <= 0
                ):
                    raise ValueError("max_tokens must be positive")
                response = {
                    "choices": [
                        {"message": {"role": "assistant", "content": "mock completion"}}
                    ]
                }
            elif path.endswith("/compatible-mode/v1/embeddings"):
                values = embedding_inputs(body)
                dimension = body.get("dimensions", 768)
                response = {
                    "data": [
                        {"index": index, "embedding": vector(dimension)}
                        for index, _ in enumerate(values)
                    ]
                }
            elif path.endswith("/v1/rerank"):
                documents = body.get("documents")
                if not isinstance(documents, list) or not documents:
                    raise ValueError("documents must be a nonempty array")
                if any(not isinstance(document, str) for document in documents):
                    raise ValueError("documents must contain strings")
                response = {
                    "results": [
                        {"index": index, "relevance_score": 1.0 / (index + 1)}
                        for index, _ in enumerate(documents)
                    ]
                }
            elif path.endswith("/api/generate"):
                prompt = body.get("prompt")
                if not isinstance(prompt, str) or not prompt:
                    raise ValueError("prompt must be a nonempty string")
                response = {"response": "mock completion"}
            elif path.endswith("/api/embed"):
                values = embedding_inputs(body)
                response = {"embeddings": [vector(4) for _ in values]}
            else:
                self.send_json(404, {"error": "unknown endpoint"})
                return
            self.send_json(200, response)
        except (ValueError, TypeError, json.JSONDecodeError) as error:
            self.send_json(400, {"error": str(error)})

    def send_json(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
