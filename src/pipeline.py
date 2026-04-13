"""Main pipeline for clone detection."""

import json
import logging
from pathlib import Path
from typing import Optional

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

            # Step 4: Summarize clone groups with LLM
            if summarize:
                logger.info("Step 3: Summarizing clone groups with LLM...")
                self._summarize_results(results)
            else:
                logger.info("Step 3: Skipping LLM summary generation")
            
            # Step 5: Save results
            logger.info("Step 4: Saving results...")
            parser.save_results(results, output_file)
            
            logger.info("Clone detection completed successfully")
            return True
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False

    def _summarize_results(self, results: list[dict]) -> None:
        """Use llm_client to summarize each func_group in-place."""
        try:
            llm_client = LLMClient()
        except Exception as e:
            logger.warning(f"LLM client unavailable, skip func_group summary: {e}")
            return

        for index, result in enumerate(results, start=1):
            func_group = result.get("func_group", [])
            if not func_group:
                result["summary"] = None
                continue

            logger.info(f"Summarizing clone group {index}/{len(results)}")
            summary = llm_client.summarize_func_group(func_group)
            result["summary"] = self._parse_summary_json(summary)

    def _parse_summary_json(self, summary: Optional[str]) -> Optional[dict]:
        """Parse LLM summary response into a JSON object."""
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
            logger.warning(f"Failed to parse LLM summary as JSON: {e}")
            return None

        required_keys = ["函数组名称","共同职责", "共同功能", "主要差异点", "可能的复用方向"]
        if not isinstance(data, dict):
            logger.warning("LLM summary is not a JSON object")
            return None

        normalized = {}
        for key in required_keys:
            value = data.get(key)
            normalized[key] = value if isinstance(value, str) else ""

        return normalized
