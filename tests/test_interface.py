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
        print(f"Successfully found {len(results)} clusters (including noise cluster if any).")
        for cluster in results[:2]:
            print(
                f"- Cluster {cluster['cluster_id']} [{cluster['cluster_type']}], "
                f"size={cluster['size']}: {cluster['files']}"
            )
    else:
        print("No clusters found or error occurred.")

if __name__ == "__main__":
    test_interface()
