"""Parse SAGA results and generate clone detection output."""

import csv
import json
import re
from pathlib import Path
from typing import Dict, List, Tuple, Any, Set
import logging


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
        self.pair_file = self.result_dir / "type123_method_pair_result.csv"
        
        # Validate files exist
        for file_path in [self.group_file, self.measure_file, self.pair_file]:
            if not file_path.exists():
                raise FileNotFoundError(f"Result file not found: {file_path}")
        
        self.measure_index: Dict[int, Tuple[str, int, int]] = {}
        self.pair_similarity: Dict[Tuple[int, int], float] = {}
    
    def parse(self) -> List[Dict[str, Any]]:
        """
        Parse all result files and generate clone groups.

        Returns:
            List of clone detection results
        """
        # Load measure index
        self._load_measure_index()
        
        # Load pair similarities
        self._load_pair_similarities()
        
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
    
    def _load_pair_similarities(self) -> None:
        """Load type123_method_pair_result.csv file."""
        try:
            with open(self.pair_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                for row in reader:
                    if len(row) >= 3:
                        idx1 = int(row[0])
                        idx2 = int(row[1])
                        similarity = float(row[2])
                        # Store both directions
                        self.pair_similarity[(idx1, idx2)] = similarity
                        self.pair_similarity[(idx2, idx1)] = similarity
            
            logger.info(f"Loaded {len(self.pair_similarity)} pair similarities")
        except Exception as e:
            logger.error(f"Failed to load pair similarities: {e}")
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
        func_paths: Dict[str, List[List[int]]] = {}
        projects: Set[str] = set()
        
        for idx in indices:
            if idx not in self.measure_index:
                logger.warning(f"Index {idx} not found in measure index")
                continue
            
            file_path, start_line, end_line = self.measure_index[idx]
            
            # Normalize path
            normalized_path = self._normalize_path(file_path)
            if normalized_path:
                if normalized_path not in func_paths:
                    func_paths[normalized_path] = []
                func_paths[normalized_path].append([start_line, end_line])
                
                # Extract project name
                project = self._extract_project_name(normalized_path)
                if project:
                    projects.add(project)
        
        if not func_paths:
            return None
        
        # Build pair similarities
        pair_similarities = self._build_pair_similarities(indices)
        
        return {
            "func_paths": func_paths,
            "relevent_projects": sorted(list(projects)),
            "pair_similarity": pair_similarities
        }
    
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
    
    def _build_pair_similarities(self, indices: List[int]) -> List[Dict[str, Any]]:
        """
        Build pair similarity information.

        Args:
            indices: List of measure indices in this group

        Returns:
            List of pair similarity objects
        """
        similarities = []
        seen_pairs = set()
        
        for i, idx1 in enumerate(indices):
            for idx2 in indices[i+1:]:
                pair_key = (min(idx1, idx2), max(idx1, idx2))
                if pair_key in seen_pairs:
                    continue
                seen_pairs.add(pair_key)
                
                similarity_score = self.pair_similarity.get(
                    pair_key,
                    self.pair_similarity.get((idx2, idx1), None)
                )
                
                if similarity_score is not None:
                    similarities.append({
                        "index_pair": [idx1, idx2],
                        "similarity": similarity_score
                    })
        
        return similarities
    
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
