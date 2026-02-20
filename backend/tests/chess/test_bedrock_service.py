from __future__ import annotations

import unittest

from fastapi import HTTPException

from app.chess.services.bedrock import _extract_text


class BedrockServiceTests(unittest.TestCase):
    def test_extract_text_reads_standard_text_blocks(self) -> None:
        response = {
            "output": {
                "message": {
                    "content": [
                        {"text": " Position is balanced. "},
                        {"text": "Develop pieces quickly."},
                    ]
                }
            }
        }

        text = _extract_text(response)
        self.assertEqual(text, "Position is balanced.\nDevelop pieces quickly.")

    def test_extract_text_ignores_reasoning_style_nested_text_blocks(self) -> None:
        response = {
            "output": {
                "message": {
                    "content": [
                        {
                            "reasoningContent": {
                                "reasoningText": {
                                    "text": "White has the initiative."
                                }
                            }
                        },
                        {"text": "Best move is Nf3."},
                    ]
                }
            }
        }

        text = _extract_text(response)
        self.assertEqual(text, "Best move is Nf3.")

    def test_extract_text_raises_when_no_text_values_exist(self) -> None:
        response = {
            "output": {
                "message": {
                    "content": [
                        {"reasoningContent": {"redactedContent": "abc123"}},
                    ]
                }
            }
        }

        with self.assertRaises(HTTPException) as raised:
            _extract_text(response)

        self.assertEqual(raised.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
