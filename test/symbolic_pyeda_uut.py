# =============================================================
# batch_check_models.py
# Chạy tất cả PNML trong một folder:
#   - BFS (explicit)
#   - DFS (explicit)
#   - SYMBOLIC BDD (Task 3)
# Và thống kê test nào đúng (match), test nào sai.
# =============================================================

import os
import sys

# Lấy đường dẫn project root = thư mục cha của thư mục test
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE_DIR = os.path.join(ROOT_DIR, "source")

# Thêm source/ vào sys.path để import được parser, reachability, symbolic_pyeda
if SOURCE_DIR not in sys.path:
    sys.path.insert(0, SOURCE_DIR)


import argparse
from typing import List, Dict, Any

from parser import parse_pnml
from reachability import Color
from symbolic_pyeda import run_explicit_search, run_symbolic_search


# Danh sách các file .pnml cần bỏ qua (theo tên file, không tính path)
# Bạn muốn bỏ thêm file nào thì thêm vào đây.
EXCLUDED_FILES = {
    "philo.pnml",
    "file2_token_ring_1safe.pnml",
    # "some_other_model.pnml",
    # "weird_case.pnml",
}


def find_pnml_files(folder: str) -> List[str]:
    """
    Tìm tất cả file .pnml trong folder (không đệ quy),
    nhưng bỏ qua các file có tên nằm trong EXCLUDED_FILES.
    """
    files = []
    # Chuẩn hóa set tên file (lowercase) để so sánh không phân biệt hoa/thường
    excluded_lower = {name.lower() for name in EXCLUDED_FILES}

    for name in os.listdir(folder):
        name_lower = name.lower()
        # Nếu file nằm trong danh sách bỏ qua thì skip
        if name_lower in excluded_lower:
            continue
        # Chỉ lấy file .pnml
        if name_lower.endswith(".pnml"):
            files.append(os.path.join(folder, name))

    return sorted(files)


def check_one_model(pnml_path: str) -> Dict[str, Any]:
    """
    Chạy BFS / DFS / BDD trên một model PNML và trả về thống kê.
    """
    result: Dict[str, Any] = {
        "file": os.path.basename(pnml_path),
        "path": pnml_path,
        "status": "UNKNOWN",
        "error": None,
        "bfs_cnt": None,
        "dfs_cnt": None,
        "bdd_cnt": None,
        "bfs_time": None,
        "dfs_time": None,
        "bdd_time": None,
    }

    try:
        net = parse_pnml(pnml_path)
        if not net:
            result["status"] = "ERROR"
            result["error"] = "parse_pnml returned None/False"
            return result

        # 1) BFS
        bfs_cnt, bfs_time, bfs_mem, bfs_list = run_explicit_search(net, "BFS")

        # 2) DFS
        dfs_cnt, dfs_time, dfs_mem, dfs_list = run_explicit_search(net, "DFS")

        # 3) BDD symbolic
        bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = run_symbolic_search(net)

        result["bfs_cnt"] = bfs_cnt
        result["dfs_cnt"] = dfs_cnt
        result["bdd_cnt"] = bdd_cnt
        result["bfs_time"] = bfs_time
        result["dfs_time"] = dfs_time
        result["bdd_time"] = bdd_time

        if bfs_cnt == dfs_cnt == bdd_cnt:
            result["status"] = "OK"
        else:
            result["status"] = "MISMATCH"

    except Exception as e:
        result["status"] = "ERROR"
        result["error"] = repr(e)

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Batch check all PNML models (BFS/DFS vs Symbolic BDD)"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default="../Standard PNMLs",
        help="Folder chứa các file .pnml (default: ../Standard PNMLs)",
    )

    args = parser.parse_args()
    folder = os.path.normpath(args.folder)

    if not os.path.isdir(folder):
        print(f"{Color.RED}Folder not found: {folder}{Color.RESET}")
        sys.exit(1)

    print(f"\n📂 Scanning folder: {folder}\n")
    pnml_files = find_pnml_files(folder)
    if not pnml_files:
        print(f"{Color.RED}No .pnml files found in this folder.{Color.RESET}")
        sys.exit(1)

    if EXCLUDED_FILES:
        print("🚫 Excluding files:")
        for name in sorted(EXCLUDED_FILES):
            print(f"  - {name}")

    print(f"\nFound {len(pnml_files)} PNML file(s) (after exclusion):")
    for f in pnml_files:
        print(f"  - {os.path.basename(f)}")

    print("\n=== RUNNING TESTS ===")
    results: List[Dict[str, Any]] = []

    for pnml_path in pnml_files:
        print(f"\n➡️  Testing: {os.path.basename(pnml_path)}")
        info = check_one_model(pnml_path)
        results.append(info)

        status = info["status"]
        if status == "OK":
            color = Color.GREEN
            icon = "✅"
        elif status == "MISMATCH":
            color = Color.RED
            icon = "❌"
        else:
            color = Color.RED
            icon = "💥"

        print(
            f"   {color}{icon} Status: {status}{Color.RESET} "
            f"(BFS={info['bfs_cnt']}, DFS={info['dfs_cnt']}, BDD={info['bdd_cnt']})"
        )

        if status == "ERROR":
            print(f"   Error: {info['error']}")

    # ---------------------------------
    # Tổng kết
    # ---------------------------------
    print("\n========================================")
    print("SUMMARY (per model)")
    print("========================================")

    ok_cnt = mismatch_cnt = error_cnt = 0

    for info in results:
        status = info["status"]
        file = info["file"]

        if status == "OK":
            color = Color.GREEN
            icon = "✅"
            ok_cnt += 1
        elif status == "MISMATCH":
            color = Color.RED
            icon = "❌"
            mismatch_cnt += 1
        else:
            color = Color.RED
            icon = "💥"
            error_cnt += 1

        bfs_cnt = info["bfs_cnt"]
        dfs_cnt = info["dfs_cnt"]
        bdd_cnt = info["bdd_cnt"]

        print(
            f"{color}{icon} {file:<30} "
            f" BFS={bfs_cnt!s:<6} DFS={dfs_cnt!s:<6} BDD={bdd_cnt!s:<6} "
            f"({status}){Color.RESET}"
        )

    print("\n----------------------------------------")
    print(f"Total models   : {len(results)}")
    print(f"OK             : {ok_cnt}")
    print(f"Mismatch       : {mismatch_cnt}")
    print(f"Error          : {error_cnt}")
    print("----------------------------------------")


if __name__ == "__main__":
    main()
