"""Main pipeline for clone detection."""

import json
import logging
import re
from pathlib import Path
from typing import Any, Optional

from .config import Config
from .saga_runner import SAGARunner
from .result_parser import ResultParser
from .llm_client import LLMClient


logger = logging.getLogger(__name__)


class CloneDetectionPipeline:
    """Execute the complete clone detection pipeline."""

    def __init__(self, config: Config, saga_dir: str = "thirdparty/saga"):
        """
        Initialize the pipeline.

        Args:
            config: Configuration object
            saga_dir: Path to SAGA directory
        """
        self.config = config
        self.saga_runner = SAGARunner(saga_dir)
        self.logger = logging.getLogger(__name__)
    
    def run(
        self,
        output_file: Optional[Path] = None,
        summarize: bool = True
    ) -> bool:
        """
        Execute the complete clone detection pipeline.

        Args:
            output_file: Optional output file path (defaults to config.output_path)
            summarize: Whether to generate LLM summaries

        Returns:
            True if successful, False otherwise
        """
        try:
            # Step 1: Get configuration
            data_path = self.config.data_path
            output_path = self.config.output_path
            
            if not output_file:
                output_file = output_path / "clone_detection_result.json"
            
            logger.info(f"Starting clone detection pipeline")
            logger.info(f"Data path: {data_path}")
            logger.info(f"Output file: {output_file}")
            
            # Step 2: Run SAGA
            logger.info("Step 1: Running SAGA clone detector...")
            if not self.saga_runner.run(data_path):
                logger.error("SAGA execution failed")
                return False
            
            # Step 3: Parse results
            logger.info("Step 2: Parsing SAGA results...")
            result_dir = self.saga_runner.get_results_path()
            
            parser = ResultParser(result_dir, data_path)
            results = parser.parse()
            
            logger.info(f"Found {len(results)} clone groups")

            logger.info("Step 3: Building Type-1 clone groups...")
            self._build_type1_groups(results)

            # Step 4: Summarize clone groups with LLM
            if summarize:
                logger.info("Step 4: Summarizing clone groups with LLM...")
                self._summarize_results(results)
            else:
                logger.info("Step 4: Skipping LLM summary generation")
            
            # Step 5: Save results
            logger.info("Step 5: Saving results...")
            parser.save_results(results, output_file)
            
            logger.info("Clone detection completed successfully")
            return True
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False

    def _build_type1_groups(self, results: list[dict]) -> None:
        """Group functions that are identical after comment and whitespace normalization."""
        for result in results:
            grouped: dict[str, list[dict[str, Any]]] = {}
            func_group = result.get("func_group", [])

            for func in func_group:
                normalized_code = self._normalize_code_for_type1(func.get("code", ""))
                grouped.setdefault(normalized_code, []).append(func)

            result["type1_group"] = [
                {
                    "group_name": "",
                    "functionality": "",
                    "functions": functions,
                }
                for functions in grouped.values()
            ]

    def _normalize_code_for_type1(self, code: str) -> str:
        """Normalize code for Type-1 grouping by removing comments and whitespace."""
        return re.sub(r"\s+", "", self._strip_js_comments(code or ""))

    def _strip_js_comments(self, code: str) -> str:
        """Strip JavaScript line/block comments while preserving quoted content."""
        result: list[str] = []
        i = 0
        length = len(code)
        state = "normal"

        while i < length:
            char = code[i]
            next_char = code[i + 1] if i + 1 < length else ""

            if state == "line_comment":
                if char == "\n":
                    result.append(char)
                    state = "normal"
                i += 1
                continue

            if state == "block_comment":
                if char == "*" and next_char == "/":
                    i += 2
                    state = "normal"
                else:
                    if char == "\n":
                        result.append(char)
                    i += 1
                continue

            if state in {"single_quote", "double_quote", "template"}:
                result.append(char)
                if char == "\\" and i + 1 < length:
                    result.append(code[i + 1])
                    i += 2
                    continue

                if (
                    (state == "single_quote" and char == "'")
                    or (state == "double_quote" and char == '"')
                    or (state == "template" and char == "`")
                ):
                    state = "normal"

                i += 1
                continue

            if char == "/" and next_char == "/":
                state = "line_comment"
                i += 2
                continue

            if char == "/" and next_char == "*":
                state = "block_comment"
                i += 2
                continue

            if char == "'":
                state = "single_quote"
            elif char == '"':
                state = "double_quote"
            elif char == "`":
                state = "template"

            result.append(char)
            i += 1

        return "".join(result)

    def _summarize_results(self, results: list[dict]) -> None:
        """Use llm_client to summarize each Type-1 group and compare them in-place."""
        try:
            llm_client = LLMClient(self.config)
        except Exception as e:
            logger.warning(f"LLM client unavailable, skip func_group summary: {e}")
            return

        for index, result in enumerate(results, start=1):
            type1_groups = result.get("type1_group", [])
            if not type1_groups:
                result["summary"] = None
                continue

            logger.info(f"Summarizing Type-1 groups for clone group {index}/{len(results)}")
            for type1_group in type1_groups:
                summary = llm_client.summarize_type1_group(type1_group.get("functions", []))
                parsed = self._parse_type1_group_summary(summary)
                if parsed:
                    type1_group.update(parsed)

            comparison = llm_client.compare_type1_groups(type1_groups)
            result["summary"] = self._parse_group_comparison_json(comparison)

    def _parse_json_response(self, summary: Optional[str]) -> Optional[dict[str, Any]]:
        """Parse a JSON object from an LLM response."""
        if not summary:
            return None

        text = summary.strip()
        # Some models prepend reasoning in think tags before the JSON payload.
        text = re.sub(r"<think\b[^>]*>.*?</think>", "", text, flags=re.S | re.I)
        text = re.sub(r"</?think\b[^>]*/?>", "", text, flags=re.I)
        text = text.strip()

        if text.startswith("```"):
            lines = text.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM summary as JSON: {e}")
            return None

        if not isinstance(data, dict):
            logger.warning("LLM summary is not a JSON object")
            return None

        return data

    def _parse_type1_group_summary(self, summary: Optional[str]) -> Optional[dict[str, str]]:
        """Parse Type-1 group summary JSON."""
        data = self._parse_json_response(summary)
        if data is None:
            return None

        normalized = {}
        for key in ["group_name", "functionality"]:
            value = data.get(key)
            normalized[key] = value if isinstance(value, str) else ""

        return normalized

    def _parse_group_comparison_json(self, summary: Optional[str]) -> Optional[dict[str, str]]:
        """Parse Type-1 group comparison JSON."""
        data = self._parse_json_response(summary)
        if data is None:
            return None

        normalized = {}
        for key in ["克隆组名称", "总体功能", "Type1组差异", "可能的复用方向"]:
            value = data.get(key)
            normalized[key] = value if isinstance(value, str) else ""

        return normalized
