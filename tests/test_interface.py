import os
import sys
from pathlib import Path

# 将项目根目录添加到 sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(root_dir))

from main import run_clone_detection

def test_interface():
    # 确保能找到根目录下的数据集和配置文件
    dir_path = root_dir / "dataset/crcn/celeri"
    config_path = root_dir / "config.yaml"
    
    print(f"Testing run_clone_detection with path: {dir_path}")
    results = run_clone_detection(dir_path, config_path=config_path)
    
    if results:
        print(f"Successfully found {len(results)} similar pairs.")
        for pair in results[:2]: # Show first 2
            print(f"- {pair['file_a']} <-> {pair['file_b']} (Sim: {pair['total_similarity']:.4f})")
    else:
        print("No clones found or error occurred.")

if __name__ == "__main__":
    test_interface()
