"""Main pipeline for clone detection."""

from pathlib import Path
from typing import Optional
import logging

from .config import Config
from .saga_runner import SAGARunner
from .result_parser import ResultParser


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
    
    def run(self, output_file: Optional[Path] = None) -> bool:
        """
        Execute the complete clone detection pipeline.

        Args:
            output_file: Optional output file path (defaults to config.output_path)

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
            
            # Step 4: Save results
            logger.info("Step 3: Saving results...")
            parser.save_results(results, output_file)
            
            logger.info("Clone detection completed successfully")
            return True
        
        except Exception as e:
            logger.error(f"Pipeline failed: {e}", exc_info=True)
            return False
