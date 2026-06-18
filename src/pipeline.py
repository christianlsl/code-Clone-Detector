"""Main pipeline for clone detection."""

import json
import logging
import re
import shutil
import tempfile
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Optional

from .config import Config
from .saga_runner import SAGARunner
from .result_parser import ResultParser
from .llm_client import LLMClient


logger = logging.getLogger(__name__)

CATEGORIES = ("PAGE", "SERVICE")


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

            # Step 2: Collect PAGE/SERVICE JS files by strict directory segment.
            categorized_files = self._collect_categorized_js_files(data_path)
            total_candidates = sum(len(files) for files in categorized_files.values())
            logger.info(f"Found {total_candidates} candidate JS files in PAGE/SERVICE directories")

            results: list[dict[str, Any]] = []
            parser_for_save: Optional[ResultParser] = None

            # Step 3: Run SAGA separately for PAGE and SERVICE.
            for category in CATEGORIES:
                files = categorized_files[category]
                logger.info(f"Category {category}: {len(files)} input files")
                if not files:
                    logger.info(f"Category {category}: no matching files, skipping")
                    continue

                with tempfile.TemporaryDirectory(prefix=f"clone_input_{category.lower()}_") as temp_dir:
                    staging_dir = Path(temp_dir)
                    self._build_staging_directory(staging_dir, data_path, files)

                    logger.info(f"Step 3 ({category}): Running SAGA clone detector...")
                    if not self.saga_runner.run(staging_dir):
                        logger.error(f"SAGA execution failed for category {category}")
                        return False

                    logger.info(f"Step 4 ({category}): Parsing SAGA results...")
                    result_dir = self.saga_runner.get_results_path()
                    parser = ResultParser(result_dir, staging_dir)
                    category_results = parser.parse()
                    parser_for_save = parser

                    logger.info(f"Category {category}: found {len(category_results)} clone groups")

                    logger.info(f"Step 5 ({category}): Building Type-1 clone groups...")
                    self._build_type1_groups(category_results)

                    logger.info(f"Step 5.1 ({category}): Calculating Type-1 group similarities...")
                    self._calculate_type1_group_similarity(category_results)

                    for result in category_results:
                        result["category"] = category

                    results.extend(category_results)

            if not results:
                logger.info("No clone groups found for PAGE/SERVICE JS files")

            # Step 4: Summarize clone groups with LLM
            if summarize:
                logger.info("Step 6: Summarizing clone groups with LLM...")
                self._summarize_results(results)
            else:
                logger.info("Step 6: Skipping LLM summary generation")
            
            # Step 7: Save results
            logger.info("Step 7: Saving results...")
            if parser_for_save is not None:
                parser_for_save.save_results(results, output_file)
            else:
                output_file.parent.mkdir(parents=True, exist_ok=True)
                with output_file.open("w", encoding="utf-8") as f:
                    json.dump([], f, indent=2, ensure_ascii=False)
                logger.info(f"Results saved to {output_file}")
            
            logger.info("Clone detection completed successfully")
            return True
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False

    def _collect_categorized_js_files(self, data_path: Path) -> dict[str, list[Path]]:
        """Collect .js files whose path segments include strict PAGE/SERVICE directory names."""
        categorized: dict[str, list[Path]] = {category: [] for category in CATEGORIES}
        for file_path in data_path.rglob("*.js"):
            if not file_path.is_file():
                continue

            parts = set(file_path.parts)
            in_page = "PAGE" in parts
            in_service = "SERVICE" in parts

            if in_page and in_service:
                logger.warning(f"Skipping ambiguous category file: {file_path}")
                continue

            if in_page:
                categorized["PAGE"].append(file_path)
            if in_service:
                categorized["SERVICE"].append(file_path)

        return categorized

    def _build_staging_directory(self, staging_dir: Path, data_path: Path, files: list[Path]) -> None:
        """Copy matched files into a temporary directory while preserving relative structure."""
        for source_file in files:
            relative_path = source_file.relative_to(data_path)
            target_file = staging_dir / relative_path
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_file, target_file)

    def _build_type1_groups(self, results: list[dict]) -> None:
        """Group functions that are identical after comment and whitespace normalization."""
        for result in results:
            grouped: dict[str, list[dict[str, Any]]] = {}
            func_group = result.get("func_group", [])

            for func in func_group:
                code = func.get("code", "")
                func["function_name"] = self._extract_function_name(code)
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

    def _calculate_type1_group_similarity(self, results: list[dict]) -> None:
        """Calculate pairwise similarity between Type-1 groups within each clone group."""
        for result in results:
            type1_groups = result.get("type1_group", [])
            similarity_pairs: list[dict[str, Any]] = []

            if len(type1_groups) < 2:
                result["type1_group_similarity"] = similarity_pairs
                continue

            normalized_codes: list[str] = []
            for type1_group in type1_groups:
                functions = type1_group.get("functions", [])
                representative_code = ""
                if functions:
                    representative_code = functions[0].get("code", "")
                normalized_codes.append(self._normalize_code_for_type1(representative_code))

            for i in range(len(type1_groups)):
                for j in range(i + 1, len(type1_groups)):
                    score = SequenceMatcher(None, normalized_codes[i], normalized_codes[j]).ratio()
                    similarity_pairs.append(
                        {
                            "group_a_index": i,
                            "group_b_index": j,
                            "similarity": round(score, 4),
                        }
                    )

            result["type1_group_similarity"] = similarity_pairs

    def _extract_function_name(self, code: str) -> list[str]:
        """Extract all function names from a JavaScript-like snippet."""
        if not code:
            return ["anonymous"]

        patterns = [
            r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\(",
            r"\b([A-Za-z_$][\w$]*)\s*=\s*function\b",
            r"\b([A-Za-z_$][\w$]*)\s*:\s*function\b",
            r"\.prototype\.([A-Za-z_$][\w$]*)\s*=\s*function\b",
            r"\b([A-Za-z_$][\w$]*)\s*=\s*\([^)]*\)\s*=>",
            r"\b([A-Za-z_$][\w$]*)\s*:\s*\([^)]*\)\s*=>",
        ]

        names: list[str] = []
        for pattern in patterns:
            for match in re.finditer(pattern, code):
                names.append(match.group(1))

        unique_names = list(dict.fromkeys(names))
        return unique_names if unique_names else ["anonymous"]

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

        unprocessed_results: list[dict[str, Any]] = []

        for index, result in enumerate(results, start=1):
            type1_groups = result.get("type1_group", [])
            raw_result: dict[str, Any] = {
                "category": result.get("category"),
                "func_group": result.get("func_group", []),
                "type1_group_outputs": [],
                "group_comparison_output": None,
            }

            if not type1_groups:
                result["summary"] = None
                unprocessed_results.append(raw_result)
                continue

            logger.info(f"Summarizing Type-1 groups for clone group {index}/{len(results)}")
            for type1_group in type1_groups:
                summary = llm_client.summarize_type1_group(type1_group.get("functions", []))
                raw_result["type1_group_outputs"].append(
                    {
                        "functions": type1_group.get("functions", []),
                        "llm_output": summary,
                    }
                )
                parsed = self._parse_type1_group_summary(summary)
                if parsed:
                    type1_group.update(parsed)

            comparison = llm_client.compare_type1_groups(type1_groups)
            raw_result["group_comparison_output"] = comparison
            result["summary"] = self._parse_group_comparison_json(comparison)
            unprocessed_results.append(raw_result)

        self._save_unprocessed_llm_results(unprocessed_results)

    def _save_unprocessed_llm_results(self, raw_results: list[dict[str, Any]]) -> None:
        """Save raw LLM outputs before parsing."""
        output_file = self.config.output_path / "clone_detection_unprocess_result.json"

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            with output_file.open("w", encoding="utf-8") as file:
                json.dump(raw_results, file, ensure_ascii=False, indent=2)
            logger.info(f"Saved unprocessed LLM outputs to {output_file}")
        except Exception as e:
            logger.warning(f"Failed to save unprocessed LLM outputs: {e}")

    def _parse_json_response(self, summary: Optional[str]) -> Optional[dict[str, Any]]:
        """Parse a JSON object from an LLM response."""
        if not summary:
            return None

        text = summary.strip()

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
            logger.warning(f"Failed to parse LLM summary as JSON: {e}，summary: {text}")
            return None

        if not isinstance(data, dict):
            logger.warning(f"LLM summary is not a JSON object，data: {data}")
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
        for key in ["group_name", "overall_functionality", "type1_group_differences", "reuse_opportunities"]:
            value = data.get(key)
            normalized[key] = value if isinstance(value, str) else ""

        return normalized
