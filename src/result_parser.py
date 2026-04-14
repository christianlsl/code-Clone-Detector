"""Parse SAGA results and generate clone detection output."""

import csv
import json
import re
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Any, Set


logger = logging.getLogger(__name__)


class ResultParser:
    """Parse SAGA output files and generate clone detection results."""

    def __init__(self, result_dir: Path, data_path: Path):
        """
        Initialize result parser.

        Args:
            result_dir: Path to SAGA result directory
            data_path: Original data path containing projects
        """
        self.result_dir = Path(result_dir)
        self.data_path = Path(data_path)
        
        self.group_file = self.result_dir / "type123_method_group_result.csv"
        self.measure_file = self.result_dir / "MeasureIndex.csv"
        
        # Validate files exist
        for file_path in [self.group_file, self.measure_file]:
            if not file_path.exists():
                raise FileNotFoundError(f"Result file not found: {file_path}")
        
        self.measure_index: Dict[int, Tuple[str, int, int]] = {}
    
    def parse(self) -> List[Dict[str, Any]]:
        """
        Parse all result files and generate clone groups.

        Returns:
            List of clone detection results
        """
        # Load measure index
        self._load_measure_index()

        # Load and process clone groups
        group_indices_list = self._load_clone_groups()
        
        # Convert groups to output format
        results = []
        for group_indices in group_indices_list:
            if len(group_indices) >= 1:  # Include all groups, even single-file ones
                result = self._build_clone_group(group_indices)
                if result:
                    results.append(result)
        
        return results
    
    def _load_measure_index(self) -> None:
        """Load MeasureIndex.csv file."""
        try:
            with open(self.measure_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 4:
                        idx = int(row[0])
                        file_path = row[1]
                        start_line = int(row[2])
                        end_line = int(row[3])
                        self.measure_index[idx] = (file_path, start_line, end_line)
            
            logger.info(f"Loaded {len(self.measure_index)} measure entries")
        except Exception as e:
            logger.error(f"Failed to load measure index: {e}")
            raise
    
    def _load_clone_groups(self) -> List[List[int]]:
        """Load and process clone groups from group result file."""
        groups: List[List[int]] = []
        
        try:
            with open(self.group_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if not row:
                        continue
                    # Each row is already one clone group.
                    group = [int(item) for item in row if item != ""]
                    if group:
                        groups.append(group)
            
            logger.info(f"Found {len(groups)} clone groups")
            return groups
        
        except Exception as e:
            logger.error(f"Failed to load clone groups: {e}")
            raise
    
    def _build_clone_group(self, indices: List[int]) -> Dict[str, Any]:
        """
        Build a clone group from indices.

        Args:
            indices: List of measure index values

        Returns:
            Clone group in output format
        """
        func_group: List[Dict[str, Any]] = []
        projects: Set[str] = set()
        
        for idx in indices:
            if idx not in self.measure_index:
                logger.warning(f"Index {idx} not found in measure index")
                continue
            
            file_path, start_line, end_line = self.measure_index[idx]
            
            # Normalize path
            normalized_path = self._normalize_path(file_path)
            if normalized_path:
                code = self._extract_code(file_path, start_line, end_line)
                func_entry = {
                    "file_path": normalized_path,
                    "start_line": start_line,
                    "end_line": end_line,
                    "code": code,
                }
                func_group.append(func_entry)
                
                # Extract project name
                project = self._extract_project_name(normalized_path)
                if project:
                    projects.add(project)
        
        if not func_group:
            return None

        return {
            "func_group": func_group,
            "relevent_projects": sorted(list(projects)),
            "type1_group": [],
            "summary": None,
        }

    def _extract_code(self, file_path: str, start_line: int, end_line: int) -> str:
        """
        Extract source code from file by line range.

        Args:
            file_path: Absolute file path from MeasureIndex.csv
            start_line: 1-based start line
            end_line: 1-based end line

        Returns:
            Extracted code snippet or empty string on failure
        """
        try:
            lines = self._read_lines_with_fallback(file_path)
            if start_line < 1 or end_line < start_line:
                return ""
            snippet = lines[start_line - 1:end_line]
            return ''.join(snippet).rstrip('\n')
        except Exception as e:
            logger.warning(f"Failed to extract code from {file_path}:{start_line}-{end_line}: {e}")
            return ""

    def _read_lines_with_fallback(self, file_path: str) -> List[str]:
        """
        Read file lines with encoding fallback for mixed-language datasets.

        Args:
            file_path: Source file path

        Returns:
            File lines with newline characters preserved
        """
        with open(file_path, 'rb') as f:
            raw = f.read()

        encodings = ["utf-8", "gb18030", "latin-1"]
        last_error = None

        for encoding in encodings:
            try:
                text = raw.decode(encoding)
                return text.splitlines(keepends=True)
            except UnicodeDecodeError as e:
                last_error = e

        # This branch should be unreachable because latin-1 can decode any byte,
        # but keep explicit failure for defensive programming.
        raise UnicodeDecodeError(
            "unknown",
            raw,
            0,
            1,
            f"Unable to decode {file_path}: {last_error}"
        )
    
    def _normalize_path(self, file_path: str) -> str:
        """
        Normalize file path to relative path from data_path.

        Args:
            file_path: File path from SAGA output

        Returns:
            Normalized relative path
        """
        try:
            abs_file_path = Path(file_path)
            abs_data_path = self.data_path.resolve()
            
            # Try direct relative_to
            rel_path = abs_file_path.relative_to(abs_data_path)
            return str(rel_path).replace('\\', '/')
        except ValueError:
            pass
        
        # Fallback: use string manipulation to find data_path component
        file_path_str = str(file_path).replace('\\', '/')
        
        # Look for data_path name in the path
        data_path_name = self.data_path.name
        idx = file_path_str.find(f"/{data_path_name}/")
        
        if idx != -1:
            relative_path = file_path_str[idx + len(data_path_name) + 1:]
            return relative_path
        
        # Last resort: extract from end of path
        logger.debug(f"Using fallback normalization for path: {file_path}")
        return file_path_str.replace('\\', '/')
    
    def _extract_project_name(self, file_path: str) -> str:
        """
        Extract project name from file path.

        Args:
            file_path: Relative file path

        Returns:
            Project name
        """
        # Expected format: {num}.{project_name}/...
        parts = file_path.split('/')
        if parts and parts[0]:
            # Match pattern like "02.sdm_df"
            match = re.match(r'(\d+)\.(.+)', parts[0])
            if match:
                return match.group(2)
            return parts[0]
        return ""
    
    def save_results(self, results: List[Dict[str, Any]], output_file: Path) -> None:
        """
        Save results to JSON file.

        Args:
            results: Clone detection results
            output_file: Output file path
        """
        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Results saved to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save results: {e}")
            raise
