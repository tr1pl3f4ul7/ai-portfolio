"""Manual smoke test for /chat against the REAL Z.AI API.

    ./run-chat.sh                 # terminal 1: serve the backend
    python smoke_chat.py          # terminal 2: ask it real questions

Run by hand against a real server. Distinct from `pytest -m live`, which
exercises the client directly: this drives the whole HTTP stack, so it is what
proves nginx, the systemd unit and CORS are right on the VM. It lives in test/
rather than tests/ so pytest never collects it.

Everything it needs is HTTP, so it runs natively on Windows even though the
server it talks to has to run in the Linux container (sqlite-vec).

Stdlib only — no httpx, no requests, no virtualenv. A script you reach for when
something might be broken should not itself need an environment to be set up
first; any `python` on PATH will do.

    python smoke_chat.py --url http://140.238.207.203    # against the VM
    python smoke_chat.py "Ask something specific?"       # one custom question
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

# Chosen to exercise different failure modes, not just to get nice answers:
# a fact that must come from one specific chunk, a question about the corpus's
# weakest area, and one the corpus genuinely cannot answer — that last one is
# the important test, because a grounded assistant must say so rather than
# invent something.
DEFAULT_QUESTIONS = [
    "Who does Ljuben currently work for?",
    "What is his experience with Flutter?",
    "Has he done any security work?",
    "Tell me about the hardest technical constraint he has worked under.",
    "What is his favourite restaurant in Brisbane?",
]


def post_json(url: str, payload: dict, timeout: float) -> dict:
    """POST JSON and return the decoded response, raising on any non-2xx."""
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ask(url: str, question: str) -> bool:
    print(f"\n\033[1;34m? {question}\033[0m")

    started = time.monotonic()
    try:
        body = post_json(f"{url}/chat", {"question": question}, timeout=60.0)
    except urllib.error.HTTPError as exc:
        # 429 and 503 arrive here, and their bodies say which one and why —
        # that detail is the whole point of reading the failure.
        print(f"\033[1;31m{exc.code}: {exc.read().decode('utf-8', 'replace')}\033[0m")
        return False
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\033[1;31mrequest failed: {exc}\033[0m")
        return False
    elapsed = time.monotonic() - started

    print(body["answer"])
    sources = ", ".join(f"{s['document']}#{s['section']}" for s in body["sources"])
    print(f"\033[2msources: {sources or '(none)'}\033[0m")
    print(f"\033[2m{elapsed:.1f}s\033[0m")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("questions", nargs="*", help="questions to ask (default: a fixed set)")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="backend base URL")
    args = parser.parse_args()

    url = args.url.rstrip("/")
    questions = args.questions or DEFAULT_QUESTIONS

    try:
        with urllib.request.urlopen(f"{url}/health", timeout=10.0):
            pass
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"\033[1;31m{url} is not answering /health: {exc}\033[0m")
        print("Start the server first:  ./run-chat.sh")
        return 1

    print(f"\033[1;32m{url} is up\033[0m")
    print("\033[2mThis calls the real Z.AI API. Free, but rate-limited - expect retries.\033[0m")

    failures = sum(not ask(url, q) for q in questions)

    print()
    if failures:
        print(f"\033[1;31m{failures}/{len(questions)} questions failed\033[0m")
        return 1

    print(f"\033[1;32mall {len(questions)} questions answered\033[0m")
    print("\033[2mRead them: are they accurate, and grounded in the sources listed?\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
