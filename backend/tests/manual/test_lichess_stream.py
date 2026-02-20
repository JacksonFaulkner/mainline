import argparse
import os
import sys

import requests


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stream a Lichess board game to validate token connectivity."
    )
    parser.add_argument("game_id", nargs="?", default="IitN6v37")
    parser.add_argument("--max-lines", type=int, default=20)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    token = os.getenv("LICHESS_TOKEN")
    if not token:
        print("Missing LICHESS_TOKEN environment variable.", file=sys.stderr)
        return 1

    url = f"https://lichess.org/api/board/game/stream/{args.game_id}"
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Connecting to {url}")
    try:
        with requests.get(
            url,
            headers=headers,
            stream=True,
            timeout=args.timeout,
        ) as response:
            print(f"HTTP {response.status_code}")
            if response.status_code >= 400:
                error_body = response.text.strip()
                if error_body:
                    print(f"Lichess error body: {error_body}", file=sys.stderr)
                return 2

            count = 0
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                print(line)
                count += 1
                if count >= args.max_lines:
                    break
    except requests.RequestException as exc:
        print(f"Request error: {exc}", file=sys.stderr)
        return 3

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
