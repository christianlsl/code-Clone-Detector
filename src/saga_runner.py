"""SAGA clone detector runner."""

import subprocess
import shutil
from pathlib import Path
from typing import Optional
import logging


logger = logging.getLogger(__name__)


class SAGARunner:
    """Handle SAGA program execution and cleanup."""

    def __init__(self, saga_dir: str = "thirdparty/saga"):
        """
        Initialize SAGA runner.

        Args:
            saga_dir: Path to SAGA directory containing SAGACloneDetector.jar
        """
        self.saga_dir = Path(saga_dir)
        self.jar_file = self.saga_dir / "SAGACloneDetector.jar"
        self.result_dir = self.saga_dir / "result"
        self.token_data_dir = self.saga_dir / "tokenData"
        self.logs_dir = self.saga_dir / "logs"
        
        if not self.jar_file.exists():
            raise FileNotFoundError(f"SAGA JAR not found: {self.jar_file}")
    
    def cleanup_previous_results(self) -> None:
        """Clean up previous SAGA output directories."""
        dirs_to_clean = [self.result_dir, self.token_data_dir, self.logs_dir]
        
        for dir_path in dirs_to_clean:
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    logger.info(f"Cleaned up: {dir_path}")
                except Exception as e:
                    logger.warning(f"Failed to clean {dir_path}: {e}")
    
    def run(self, data_path: Path) -> bool:
        """
        Run SAGA clone detector on the given data path.

        Args:
            data_path: Path to JS files directory

        Returns:
            True if successful, False otherwise
        """
        if not data_path.exists():
            logger.error(f"Data path not found: {data_path}")
            return False
        
        # Clean previous results
        self.cleanup_previous_results()
        
        # Convert to absolute paths
        abs_data_path = data_path.resolve()
        abs_jar_file = self.jar_file.resolve()
        
        # Prepare command with absolute paths
        cmd = ["java", "-jar", str(abs_jar_file), str(abs_data_path)]
        
        try:
            logger.info(f"Running SAGA with command: {' '.join(cmd)}")
            result = subprocess.run(
                cmd,
                cwd=str(self.saga_dir.resolve()),
                capture_output=True,
                text=True,
                timeout=3600  # 1 hour timeout
            )
            
            if result.returncode == 0:
                logger.info("SAGA execution completed successfully")
                logger.debug(f"SAGA stdout: {result.stdout}")
                return True
            else:
                logger.error(f"SAGA execution failed with code {result.returncode}")
                logger.error(f"SAGA stderr: {result.stderr}")
                return False
        
        except subprocess.TimeoutExpired:
            logger.error("SAGA execution timed out")
            return False
        except Exception as e:
            logger.error(f"Failed to run SAGA: {e}")
            return False
    
    def get_results_path(self) -> Path:
        """Get path to SAGA results directory."""
        return self.result_dir
