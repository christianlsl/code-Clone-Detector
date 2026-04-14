"""Main entry point for clone detection program."""

import argparse
import sys
import logging
from pathlib import Path

from src.config import Config
from src.logger_setup import setup_logger
from src.pipeline import CloneDetectionPipeline


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="JavaScript Code Clone Detection using SAGA"
    )
    parser.add_argument(
        "-i", "--input",
        help="Input data path (optional, overrides config)"
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (optional, overrides config)"
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="Skip LLM summary generation"
    )
    
    args = parser.parse_args()
    
    try:
        # Load configuration
        config = Config()

        # Override config data_path when input argument is provided
        if args.input:
            config.config["data_path"] = args.input
        
        # Setup logging
        log_level = logging.INFO
        root_logger = setup_logger("clone_detector", config.log_path, log_level)
        
        # Configure root logger to propagate to our logger
        logging.getLogger().setLevel(log_level)
        
        logger = logging.getLogger("clone_detector")
        logger.info(f"Configuration loaded from {config.config_file}")
        logger.info(f"Data path: {config.data_path}")
        logger.info(f"Output path: {config.output_path}")
        logger.info(f"Log path: {config.log_path}")
        logger.info(f"LLM provider: {config.llm_provider}")
        
        # Run pipeline
        pipeline = CloneDetectionPipeline(config)
        output_file = Path(args.output) if args.output else None
        
        success = pipeline.run(output_file, summarize=not args.no_summary)
        
        logger.info(f"Execution {'completed successfully' if success else 'failed'}")
        
        return 0 if success else 1
    
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
