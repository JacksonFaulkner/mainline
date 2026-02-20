from __future__ import annotations

import unittest
from unittest.mock import patch

import chess

from app.chess.schemas.api import CommentaryAnalysisStreamRequest
from app.chess.schemas.review import BedrockCompletion
from app.chess.services.commentary_analysis_stream import (
    _build_prompt,
    _parse_structured_commentary,
    stream_commentary_analysis,
)


class _FakeClient:
    def converse_stream(self, **_: object) -> dict[str, object]:
        # Stream has metadata and stop signals, but no contentBlockDelta text.
        return {
            "stream": iter(
                [
                    {"messageStart": {"role": "assistant"}},
                    {"contentBlockStart": {"contentBlockIndex": 0}},
                    {"contentBlockStop": {"contentBlockIndex": 0}},
                    {"messageStop": {"stopReason": "end_turn"}},
                    {"metadata": {"usage": {"inputTokens": 11, "outputTokens": 22, "totalTokens": 33}}},
                ]
            )
        }


class _FakeReasoningDeltaClient:
    def converse_stream(self, **_: object) -> dict[str, object]:
        return {
            "stream": iter(
                [
                    {
                        "contentBlockDelta": {
                            "delta": {
                                "reasoningContent": {
                                    "reasoningText": {
                                        "text": "This is reasoning output. "
                                    }
                                }
                            }
                        }
                    },
                    {
                        "contentBlockDelta": {
                            "delta": {
                                "text": "Final answer."
                            }
                        }
                    },
                    {"messageStop": {"stopReason": "end_turn"}},
                ]
            )
        }


class _FakeStructuredJsonClient:
    def converse_stream(self, **_: object) -> dict[str, object]:
        return {
            "stream": iter(
                [
                    {
                        "contentBlockDelta": {
                            "delta": {
                                "text": (
                                    '{"position_plan_title":"Queenside Push",'
                                    '"advantage_side":"white","advantage_summary":"White has the safer king and more active pieces",'
                                    '"best_move_san":"Nf3","best_move_reason":"it develops with tempo and covers key central squares",'
                                    '"danger_to_watch":"allowing ...d5 breaks if White delays development",'
                                    '"white_plan":["Push queenside pawns","Keep the king safe"],'
                                    '"black_plan":["Challenge the center","Seek knight activity"],'
                                    '"concrete_ideas":[{"title":"Control d5","description":"White can seize d5 and restrict Black counterplay",'
                                    '"selected_line_id":"L01","playback_pv_uci":["c2c4","e7e6","b1c3"]}]}'
                                )
                            }
                        }
                    },
                    {"messageStop": {"stopReason": "end_turn"}},
                ]
            )
        }


class CommentaryAnalysisStreamTests(unittest.TestCase):
    def test_prompt_requires_single_json_object_schema(self) -> None:
        params = CommentaryAnalysisStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
            stockfish_context="Depth 10. Best move Nf3 (+0.20). Top lines: #1 Nf3 (+0.20)",
        )
        prompt = _build_prompt(params, chess.Board(params.fen))

        self.assertIn("exactly one json object", prompt.system_prompt.lower())
        self.assertIn('"position_plan_title"', prompt.user_message)
        self.assertIn('"advantage_side"', prompt.user_message)
        self.assertIn('"best_move_san"', prompt.user_message)
        self.assertIn('"white_plan"', prompt.user_message)
        self.assertIn('"black_plan"', prompt.user_message)
        self.assertIn('"concrete_ideas"', prompt.user_message)
        self.assertIn("less than 5 words", prompt.user_message.lower())
        self.assertIn("san notation", prompt.user_message.lower())
        self.assertLessEqual(prompt.max_output_tokens, 320)
        self.assertTrue(
            any(line.label == "Stockfish context" for line in prompt.context_lines)
        )

    def test_stream_falls_back_to_converse_when_stream_yields_no_text(self) -> None:
        params = CommentaryAnalysisStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        fallback = BedrockCompletion(
            model_id="arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
            text="Fallback text from converse call.",
            stop_reason="end_turn",
            latency_ms=123,
        )

        with patch(
            "app.chess.services.commentary_analysis_stream._build_runtime_client",
            return_value=(_FakeClient(), Exception, Exception),
        ), patch(
            "app.chess.services.commentary_analysis_stream.converse_bedrock_review",
            return_value=fallback,
        ):
            events = list(stream_commentary_analysis(params))

        self.assertGreaterEqual(len(events), 2)
        self.assertEqual(events[-1]["type"], "commentary_complete")
        self.assertEqual(events[-1]["text"], "Fallback text from converse call.")
        self.assertIsNone(events[-1].get("structured"))
        self.assertTrue(any(event["type"] == "commentary_text_delta" for event in events))
        self.assertFalse(any(event["type"] == "commentary_error" for event in events))

    def test_stream_emits_error_when_fallback_completion_is_empty(self) -> None:
        params = CommentaryAnalysisStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )
        empty_fallback = BedrockCompletion(
            model_id="arn:aws:bedrock:us-east-1:762185908994:inference-profile/us.anthropic.claude-haiku-4-5-20251001-v1:0",
            text="   ",
            stop_reason="end_turn",
            latency_ms=100,
        )

        with patch(
            "app.chess.services.commentary_analysis_stream._build_runtime_client",
            return_value=(_FakeClient(), Exception, Exception),
        ), patch(
            "app.chess.services.commentary_analysis_stream.converse_bedrock_review",
            return_value=empty_fallback,
        ):
            events = list(stream_commentary_analysis(params))

        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[-1]["type"], "commentary_error")
        self.assertEqual(events[-1]["code"], "empty_completion")
        self.assertFalse(any(event["type"] == "commentary_complete" for event in events))

    def test_stream_ignores_reasoning_delta_and_emits_final_text(self) -> None:
        params = CommentaryAnalysisStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )

        with patch(
            "app.chess.services.commentary_analysis_stream._build_runtime_client",
            return_value=(_FakeReasoningDeltaClient(), Exception, Exception),
        ), patch(
            "app.chess.services.commentary_analysis_stream.converse_bedrock_review"
        ) as fallback_mock:
            events = list(stream_commentary_analysis(params))

        self.assertTrue(any(event["type"] == "commentary_text_delta" for event in events))
        self.assertEqual(events[-1]["type"], "commentary_complete")
        self.assertIn("Final answer.", events[-1]["text"])
        self.assertNotIn("reasoning output", events[-1]["text"])
        fallback_mock.assert_not_called()

    def test_stream_parses_structured_json_into_complete_event(self) -> None:
        params = CommentaryAnalysisStreamRequest(
            fen="rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"
        )

        with patch(
            "app.chess.services.commentary_analysis_stream._build_runtime_client",
            return_value=(_FakeStructuredJsonClient(), Exception, Exception),
        ), patch(
            "app.chess.services.commentary_analysis_stream.converse_bedrock_review"
        ) as fallback_mock:
            events = list(stream_commentary_analysis(params))

        self.assertEqual(events[-1]["type"], "commentary_complete")
        structured = events[-1].get("structured")
        self.assertIsInstance(structured, dict)
        assert isinstance(structured, dict)
        self.assertEqual(structured.get("position_plan_title"), "Queenside Push")
        self.assertEqual(structured.get("advantage_side"), "white")
        self.assertEqual(structured.get("best_move_san"), "Nf3")
        self.assertEqual(len(structured.get("white_plan", [])), 2)
        self.assertEqual(len(structured.get("black_plan", [])), 2)
        ideas = structured.get("concrete_ideas", [])
        self.assertEqual(len(ideas), 1)
        self.assertEqual(ideas[0]["selected_line_id"], "L01")
        self.assertEqual(ideas[0]["playback_pv_uci"][0], "c2c4")
        self.assertIn("Best move is Nf3", events[-1]["text"])
        fallback_mock.assert_not_called()

    def test_parse_structured_commentary_recovers_fenced_json_with_preface(self) -> None:
        raw = (
            "Here is the requested output.\n"
            "```json\n"
            '{\n'
            '  "position_plan_title": "Center Tension",\n'
            '  "advantage_side": "equal",\n'
            '  "advantage_summary": "Both sides are developed and central tension remains.",\n'
            '  "best_move_san": "Nc6",\n'
            '  "best_move_reason": "Develops with tempo and increases central pressure.",\n'
            '  "danger_to_watch": "A delayed king safety plan can allow tactical shots.",\n'
            '  "white_plan": ["Castle kingside", "Stabilize d4 with c3"],\n'
            '  "black_plan": ["Develop bishop", "Pressure d4 with pieces"],\n'
            '  "concrete_ideas": [\n'
            '    {\n'
            '      "title": "Pressure d4",\n'
            '      "description": "Coordinate pieces to increase pressure on d4.",\n'
            '      "selected_line_id": "L01",\n'
            '      "playback_pv_uci": ["b8c6", "g1f3", "e7e6"]\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```"
        )

        structured = _parse_structured_commentary(raw)
        self.assertIsNotNone(structured)
        assert structured is not None
        self.assertEqual(structured.position_plan_title, "Center Tension")
        self.assertEqual(structured.advantage_side, "equal")
        self.assertEqual(structured.concrete_ideas[0].selected_line_id, "L01")

    def test_parse_structured_commentary_repairs_trailing_commas(self) -> None:
        raw = (
            '{'
            '"position_plan_title":"Stable Center",'
            '"advantage_side":"equal",'
            '"advantage_summary":"Central tension is balanced.",'
            '"best_move_san":"Nc6",'
            '"best_move_reason":"Develops and contests d4.",'
            '"danger_to_watch":"White may gain space with d5.",'
            '"white_plan":["Castle kingside","Support d4"],'
            '"black_plan":["Develop bishop","Challenge center"],'
            '"concrete_ideas":[{"title":"Hit d4","description":"Increase pressure on d4.",'
            '"selected_line_id":"L01","playback_pv_uci":["b8c6","g1f3",],},],'
            '}'
        )

        structured = _parse_structured_commentary(raw)
        self.assertIsNotNone(structured)
        assert structured is not None
        self.assertEqual(structured.best_move_san, "Nc6")
        self.assertEqual(len(structured.concrete_ideas), 1)


if __name__ == "__main__":
    unittest.main()
