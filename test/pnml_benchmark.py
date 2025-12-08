import os
import sys
import time
import glob
import argparse
import contextlib
import traceback
from typing import List, Dict


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"
    GRAY = "\033[90m"


# ========== CẤU HÌNH ĐƯỜNG DẪN ==========
# Thư mục chứa chính file benchmark_runner.py (tức là .../MM-251-ASSIGNMENT/test)
THIS_DIR = os.path.dirname(os.path.abspath(__file__))

# Thư mục gốc project: cha của test/
PROJECT_ROOT = os.path.abspath(os.path.join(THIS_DIR, ".."))

# Thư mục chứa code bài tập lớn
SOURCE_DIR = os.path.join(PROJECT_ROOT, "source")

# Thêm SOURCE_DIR (và PROJECT_ROOT nếu muốn) vào sys.path để import được các module trong source
for p in (SOURCE_DIR, PROJECT_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

# ========== IMPORT MODULE TỪ source ==========
try:
    # LƯU Ý: giờ import KHÔNG dùng prefix "source."
    from parser import parse_pnml
    from reachability import build_place_index
    from symbolic_computation_BDD import run_symbolic_search, run_explicit_search

    from deadlock_detection import build_dead_formula, extract_marking_from_bdd

    try:
        from deadlock_detection_cegar import check_deadlock_cegar
    except ImportError:
        check_deadlock_cegar = None

except ImportError as e:
    print(f"{Color.RED}❌ Lỗi Import: {e}{Color.RESET}")
    print("Hãy đảm bảo toàn bộ code nằm trong folder 'source'.")
    # In thêm traceback cho dễ debug nếu còn lỗi
    traceback.print_exc()
    sys.exit(1)


# =============================================================
# UTILS
# =============================================================
@contextlib.contextmanager
def suppress_stdout():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        sys.stdout = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout


def format_marking(marking_vec: List[int], place_order: List[str], net) -> str:
    if not marking_vec:
        return "N/A"
    active = []
    for i, val in enumerate(marking_vec):
        if val > 0:
            p_id = place_order[i]
            p_obj = net.places.get(p_id)
            name = str(p_obj.name) if p_obj and hasattr(p_obj, "name") and p_obj.name else str(p_id)
            active.append(name)
    return ", ".join(active) if active else "Empty"


# =============================================================
# BENCHMARK ENGINE
# =============================================================

def run_benchmark_on_file(filepath: str):
    filename = os.path.basename(filepath)
    print(f"Processing: {Color.CYAN}{filename:<30}{Color.RESET}", end="\r")

    try:
        net = parse_pnml(filepath)
        if not net:
            return None
        num_places = len(net.places)

        # ---------------------------------------------------------
        # TASK 2: EXPLICIT REACHABILITY
        # ---------------------------------------------------------
        # BFS
        start = time.perf_counter()
        with suppress_stdout():
            bfs_cnt, _, _, _ = run_explicit_search(net, "BFS")
        bfs_time = (time.perf_counter() - start) * 1000

        # DFS
        start = time.perf_counter()
        with suppress_stdout():
            dfs_cnt, _, _, _ = run_explicit_search(net, "DFS")
        dfs_time = (time.perf_counter() - start) * 1000

        # ---------------------------------------------------------
        # TASK 3: SYMBOLIC REACHABILITY (Dùng chung)
        # ---------------------------------------------------------
        start = time.perf_counter()
        with suppress_stdout():
            sym_cnt, _, _, S_reach, bdd_mgr = run_symbolic_search(net)
        sym_time = (time.perf_counter() - start) * 1000

        # ---------------------------------------------------------
        # TASK 4A: CEGAR (Code cũ)
        # ---------------------------------------------------------
        cegar_time = -1
        cegar_example = "N/A"

        if check_deadlock_cegar:
            try:
                start_c = time.perf_counter()
                with suppress_stdout():
                    has_deadlock_cegar, cegar_example = check_deadlock_cegar(net, S_reach, bdd_mgr)
                cegar_time = (time.perf_counter() - start_c) * 1000
            except Exception:
                cegar_time = -1
                cegar_example = "N/A"

        # ---------------------------------------------------------
        # TASK 4B: SYMBOLIC INTERSECTION (Code mới)
        # ---------------------------------------------------------
        start_sym = time.perf_counter()
        place_order, _ = build_place_index(net)
        x_ids = [bdd_mgr.var(f"x_{p}") for p in place_order]

        dead_condition = build_dead_formula(bdd_mgr, net, place_order, x_ids)
        deadlock_set = bdd_mgr.land(S_reach, dead_condition)

        has_deadlock = (deadlock_set != bdd_mgr.bdd.false)
        sym_example = "N/A"

        if has_deadlock:
            dead_vec = extract_marking_from_bdd(bdd_mgr, deadlock_set, place_order)
            sym_example = format_marking(dead_vec, place_order, net)

        my_time = (time.perf_counter() - start_sym) * 1000

        # Tính Speedup
        speedup = 0
        if cegar_time > 0 and my_time > 0:
            speedup = cegar_time / my_time

        print(f"{' ' * 80}", end="\r")

        return {
            "Model": filename,
            "# Places": num_places,
            "Reachable States": sym_cnt,
            "BFS Time": bfs_time,
            "DFS Time": dfs_time,
            "Sym Time": sym_time,

            # Deadlock Data
            "Deadlock?": "YES" if has_deadlock else "NO",
            "T_CEGAR": cegar_time,
            "T_Symbolic": my_time,
            "Speedup": speedup,
            "Ex_Symbolic": sym_example,
            "Ex_CEGAR": cegar_example,
        }

    except Exception as e:
        print(f"\n{Color.RED}Error: {e}{Color.RESET}")
        return None


# =============================================================
# PRINTING FUNCTIONS
# =============================================================

def print_table_1(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 1: Reachability Analysis (Explicit vs Symbolic){Color.RESET}")
    columns = [
        ("Model", 30, "Model"),
        ("#P", 4, "# Places"),
        ("#Reachable", 12, "Reachable States"),
        ("BFS [ms]", 12, "BFS Time"),
        ("DFS [ms]", 12, "DFS Time"),
        ("BDD [ms]", 12, "Sym Time"),
    ]
    _print_generic_table(data, columns)


def print_table_2(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 2: Symbolic Deadlock Detection Results (Optimized Method){Color.RESET}")
    columns = [
        ("Model", 30, "Model"),
        ("Deadlock?", 10, "Deadlock?"),
        ("Time [ms]", 12, "T_Symbolic"),
        ("Example deadlock marking", 60, "Ex_Symbolic"),
    ]
    _print_generic_table(data, columns)


def print_table_3_comparison(data: List[Dict]):
    print(f"\n{Color.BOLD}Table 3: Performance Comparison (CEGAR vs Symbolic Intersection){Color.RESET}")
    print(f"{Color.GRAY}(T.Symbolic is your optimized method. Speedup = T.CEGAR / T.Symbolic){Color.RESET}")

    columns = [
        ("Model", 30, "Model"),
        ("T. CEGAR [ms]", 15, "T_CEGAR"),
        ("T. Symbolic [ms]", 16, "T_Symbolic"),
        ("Speedup", 10, "Speedup"),
        ("Result", 8, "Deadlock?"),
        ("Example (Symbolic)", 35, "Ex_Symbolic"),
        ("Example (CEGAR)", 35, "Ex_CEGAR"),
    ]

    header, sep = _build_header_and_sep(columns)
    print(sep)
    print(header)
    print(sep)

    for row in data:
        cell_blocks = []

        for _, w, key in columns:
            val = row.get(key, "")

            if key == "Speedup":
                sp = float(val)
                base = f"{sp:.1f}x"
                if sp > 10:
                    inner = f"{Color.GREEN}{base:>{w}}{Color.RESET}"
                elif sp < 1:
                    inner = f"{Color.RED}{base:>{w}}{Color.RESET}"
                else:
                    inner = f"{base:>{w}}"

            elif key in ("T_CEGAR", "T_Symbolic"):
                if val == -1:
                    inner = f"{Color.RED}{'N/A':>{w}}{Color.RESET}"
                else:
                    inner = f"{float(val):>{w}.4f}"

            elif key == "Deadlock?":
                c = Color.RED if val == "YES" else Color.GREEN
                inner = f"{c}{val:^{w}}{Color.RESET}"

            elif "Ex_" in key:
                text = str(val)
                if len(text) > w:
                    text = text[:w - 3] + "..."
                if text == "N/A":
                    inner = f"{Color.GRAY}{text:<{w}}{Color.RESET}"
                else:
                    inner = f"{Color.YELLOW}{text:<{w}}{Color.RESET}"

            else:
                inner = f"{str(val):<{w}}"

            cell_blocks.append(f" {inner} ")

        line = "|" + "|".join(cell_blocks) + "|"
        print(line)

    print(sep)


def _build_header_and_sep(columns):
    """
    columns: list of (title, width, key)
    return: (header_line, separator_line)
    """
    # Header: mỗi ô có 1 space trái + nội dung + 1 space phải
    header_cells = [f" {title:<{w}} " for title, w, _ in columns]
    header = "|" + "|".join(header_cells) + "|"

    # Separator: cùng chiều rộng với header, nhưng dùng '-' và '+'
    sep_cells = ["-" * (w + 2) for _, w, _ in columns]
    sep = "+" + "+".join(sep_cells) + "+"

    return header, sep


def _print_generic_table(data, columns):
    header, sep = _build_header_and_sep(columns)
    print(sep)
    print(header)
    print(sep)

    for row in data:
        cell_blocks = []

        for _, w, key in columns:
            val = row.get(key, "")

            # Số trạng thái reachable
            if key == "Reachable States":
                v = int(val)
                val_str = f"{v:,}" if len(str(v)) <= w else f"{v:.1e}"
                inner = f"{val_str:>{w}}"  # canh phải

            # Các cột thời gian (ms)
            elif key in ("BFS Time", "DFS Time", "Sym Time", "T_Symbolic", "T_CEGAR", "Time [ms]"):
                try:
                    inner = f"{float(val):>{w}.4f}"
                except (TypeError, ValueError):
                    inner = f"{str(val):>{w}}"

            # Cột Deadlock? có màu
            elif key == "Deadlock?":
                c = Color.RED if val == "YES" else Color.GREEN
                inner = f"{c}{val:^{w}}{Color.RESET}"

            # Các cột Example (Ex_*)
            elif "Ex_" in key:
                text = str(val)
                if len(text) > w:
                    text = text[:w - 3] + "..."
                inner = f"{Color.YELLOW}{text:<{w}}{Color.RESET}"

            # Mặc định: text canh trái
            else:
                inner = f"{str(val):<{w}}"

            # Bọc thêm 1 space hai bên để khớp với header
            cell_blocks.append(f" {inner} ")

        line = "|" + "|".join(cell_blocks) + "|"
        print(line)

    print(sep)


# =============================================================
# MAIN
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    # LUÔN trỏ tới Standard PNMLs ở PROJECT_ROOT, không phụ thuộc thư mục bạn đang đứng
    default_dir = os.path.join(PROJECT_ROOT, "Standard PNMLs")

    parser.add_argument("--dir", type=str, default=default_dir)
    args = parser.parse_args()

    if os.path.isdir(args.dir):
        files = glob.glob(os.path.join(args.dir, "*.pnml"))
    else:
        files = glob.glob(args.dir)
    if not files:
        files = glob.glob("*.pnml")

    if not files:
        print(f"{Color.YELLOW}⚠️ No .pnml files found.{Color.RESET}")
        sys.exit(0)

    files.sort()
    print(f"{Color.BOLD}🚀 Starting Benchmark on {len(files)} files...{Color.RESET}")

    results = []
    for f in files:
        res = run_benchmark_on_file(f)
        if res:
            results.append(res)

    # In 3 bảng
    print_table_1(results)
    print("\n" + " " * 30 + "---" * 5 + "\n")
    print_table_2(results)
    print("\n" + " " * 30 + "---" * 5 + "\n")
    print_table_3_comparison(results)

    print(f"\nGenerated at: {time.strftime('%H:%M:%S')}")