# =============================================================
# symbolic_computation_BDD.py (FINAL INTEGRATED VERSION)
# Task 3: Symbolic Reachability + Comparison + Readable Logic
# Tối ưu: Pure Python BDD (Interleaved Vars + Structural Rename)
# Tích hợp: Gọi BFS/DFS từ reachability.py
# =============================================================

import os
import time
import tracemalloc
import sys
import argparse
from typing import List, Dict, Tuple

# Tăng giới hạn đệ quy để in được công thức dài và duyệt cây sâu
sys.setrecursionlimit(50000)

# --- IMPORT TỪ REACHABILITY.PY ---
try:
    from parser import parse_pnml, PetriNet
    from reachability import (
        reachable_markings_bfs,
        reachable_markings_dfs,
        build_place_index,
        pretty_marking_vec,  # Hàm in marking đẹp từ file cũ
        auto_group_places
    )
except ImportError as e:
    print(f"Lỗi import: {e}")
    print("Đảm bảo file 'reachability.py' và 'parser.py' nằm cùng thư mục.")
    sys.exit(1)


# =============================================================
# ANSI Colors
# =============================================================
class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


# =============================================================
# PART 1: OPTIMIZED PURE PYTHON BDD CLASS
# =============================================================
class BDD:
    def __init__(self, var_order: List[str]):
        # Mapping biến -> level (0 là root, càng lớn càng gần lá)
        self.var2level = {name: i for i, name in enumerate(var_order)}
        self.level2var = {i: name for i, name in enumerate(var_order)}
        self.uniq = {}
        self.nodes = {}
        self.ite_cache = {}
        self.exists_cache = {}

        # Node 0 (False), Node 1 (True) - Level max
        limit = len(var_order)
        self.uniq[(limit, 0, 0)] = 0
        self.uniq[(limit, 1, 1)] = 1
        self.nodes[0] = (limit, 0, 0)
        self.nodes[1] = (limit, 1, 1)

    def var(self, name: str) -> int:
        lvl = self.var2level[name]
        return self._mk(lvl, 0, 1)

    def _mk(self, lvl, low, high) -> int:
        if low == high: return low
        key = (lvl, low, high)
        if key in self.uniq: return self.uniq[key]
        node_id = len(self.nodes)
        self.uniq[key] = node_id
        self.nodes[node_id] = (lvl, low, high)
        return node_id

    def top_level(self, u: int):
        return self.nodes[u][0]

    def cof(self, u: int, lvl: int, val: int) -> int:
        u_lvl, low, high = self.nodes[u]
        if u_lvl > lvl: return u
        if u_lvl == lvl: return high if val == 1 else low
        return u

    def ite(self, i: int, t: int, e: int) -> int:
        if i == 1: return t
        if i == 0: return e
        if t == e: return t

        key = (i, t, e)
        if key in self.ite_cache: return self.ite_cache[key]

        lvl_i, lvl_t, lvl_e = self.top_level(i), self.top_level(t), self.top_level(e)
        top = min(lvl_i, lvl_t, lvl_e)

        # Đệ quy xuống
        r_low = self.ite(self.cof(i, top, 0), self.cof(t, top, 0), self.cof(e, top, 0))
        r_high = self.ite(self.cof(i, top, 1), self.cof(t, top, 1), self.cof(e, top, 1))

        res = self._mk(top, r_low, r_high)
        self.ite_cache[key] = res
        return res

    # Toán tử logic cơ bản
    def land(self, a: int, b: int) -> int:
        return self.ite(a, b, 0)

    def lor(self, a: int, b: int) -> int:
        return self.ite(a, 1, b)

    def lnot(self, a: int) -> int:
        return self.ite(a, 0, 1)

    # Existential Quantification: exists x. f
    def exists(self, u: int, var_levels: set) -> int:
        key = (u, id(var_levels))  # Dùng id của set để cache key nhanh
        if key in self.exists_cache: return self.exists_cache[key]

        u_lvl = self.top_level(u)
        if u_lvl >= len(self.var2level): return u

        low, high = self.nodes[u][1], self.nodes[u][2]

        if u_lvl in var_levels:
            # Nếu gặp biến cần khử -> OR 2 nhánh con
            res = self.lor(self.exists(low, var_levels), self.exists(high, var_levels))
        else:
            # Không phải biến cần khử -> Giữ nguyên node, đệ quy xuống con
            res = self._mk(u_lvl, self.exists(low, var_levels), self.exists(high, var_levels))

        self.exists_cache[key] = res
        return res

    def satcount(self, u: int, n_vars: int) -> int:
        """Đếm số nghiệm"""
        memo = {}

        def count(node, lvl):
            if node == 0: return 0
            if node == 1: return 2 ** (n_vars - lvl)
            if (node, lvl) in memo: return memo[(node, lvl)]

            n_lvl, low, high = self.nodes[node]
            factor = 2 ** (n_lvl - lvl)
            res = factor * (count(low, n_lvl + 1) + count(high, n_lvl + 1))
            memo[(node, lvl)] = res
            return res

        return int(count(u, 0))

    # --- HÀM IN CÔNG THỨC DNF ---
    def to_dnf_string(self, u: int) -> str:
        if u == 0: return "False"
        if u == 1: return "True"

        paths = []

        def collect_paths(node, current_path):
            if node == 0: return
            if node == 1:
                paths.append(current_path[:])
                return
            if len(paths) > 50: return  # Giới hạn in để tránh quá dài

            lvl, low, high = self.nodes[node]
            name = self.level2var[lvl]

            # Chỉ in biến trạng thái hiện tại (không in biến xp) cho gọn
            if not name.startswith("xp_"):
                # Nhánh High (1)
                current_path.append(name)
                collect_paths(high, current_path)
                current_path.pop()

                # Nhánh Low (0)
                current_path.append(f"!{name}")
                collect_paths(low, current_path)
                current_path.pop()
            else:
                # Nếu là biến xp (trung gian), cứ đi tiếp mà không ghi vào path
                collect_paths(high, current_path)
                collect_paths(low, current_path)

        collect_paths(u, [])
        if not paths: return "True (Dependent only on xp vars?)"

        clauses = ["(" + " & ".join(p) + ")" for p in paths]
        if len(clauses) > 50: clauses.append("...")
        return " \n| ".join(clauses)


# =============================================================
# PART 2: SYMBOLIC REACHABILITY LOGIC (OPTIMIZED)
# =============================================================

def build_optimized_relation(bdd: BDD, net: PetriNet, place_order: List[str], x_ids: List[int],
                             xp_ids: List[int]) -> int:
    """Xây dựng quan hệ chuyển trạng thái R(x, x')"""
    pid_to_idx = {pid: i for i, pid in enumerate(place_order)}
    R = 0  # False

    # Pre-compute Identity (x == x') cho phần quán tính
    identities = []
    for i in range(len(place_order)):
        # (x & x') | (!x & !x')
        eq = bdd.lor(bdd.land(x_ids[i], xp_ids[i]),
                     bdd.land(bdd.lnot(x_ids[i]), bdd.lnot(xp_ids[i])))
        identities.append(eq)

    for t_id in net.transitions:
        pre = {pid for pid, w in net.input_arcs.get(t_id, [])}
        post = {pid for pid, w in net.output_arcs.get(t_id, [])}

        # 1. Enable Condition: Pre=1, Post(strict)=0
        En = 1
        for pid in pre:
            En = bdd.land(En, x_ids[pid_to_idx[pid]])
        for pid in (post - pre):
            En = bdd.land(En, bdd.lnot(x_ids[pid_to_idx[pid]]))

        if En == 0: continue

        # 2. Update Logic: Change + Inertia
        NextState = 1
        changed_indices = set()

        # Consumed -> x'=0
        for pid in (pre - post):
            idx = pid_to_idx[pid]
            NextState = bdd.land(NextState, bdd.lnot(xp_ids[idx]))
            changed_indices.add(idx)
        # Produced -> x'=1
        for pid in post:
            idx = pid_to_idx[pid]
            NextState = bdd.land(NextState, xp_ids[idx])
            changed_indices.add(idx)
        # Inertia -> x'=x
        for i in range(len(place_order)):
            if i not in changed_indices:
                NextState = bdd.land(NextState, identities[i])

        # Combine: Rt = En & NextState
        Rt = bdd.land(En, NextState)
        R = bdd.lor(R, Rt)

    return R


def run_symbolic_search_pure(net: PetriNet):
    place_order, _ = build_place_index(net)
    num_places = len(place_order)

    # 1. Variable Ordering Tối Ưu: Xen kẽ (Interleaved)
    # x0, xp0, x1, xp1... giúp giảm kích thước BDD trung gian
    var_order = []
    for p in place_order:
        var_order.append(f"x_{p}")  # Level 2*i
        var_order.append(f"xp_{p}")  # Level 2*i + 1

    bdd = BDD(var_order)

    # Cache ID
    x_ids = [bdd.var(f"x_{p}") for p in place_order]
    xp_ids = [bdd.var(f"xp_{p}") for p in place_order]

    # Set level của biến x để dùng cho hàm exists
    x_levels = {bdd.var2level[f"x_{p}"] for p in place_order}

    tracemalloc.start()
    start_time = time.perf_counter()

    # 2. Trạng thái ban đầu S0
    S = 1  # True
    for i, pid in enumerate(place_order):
        val = net.places[pid].initial_marking
        if val > 0:
            S = bdd.land(S, x_ids[i])
        else:
            S = bdd.land(S, bdd.lnot(x_ids[i]))

    # 3. Xây dựng Transition Relation R
    R = build_optimized_relation(bdd, net, place_order, x_ids, xp_ids)

    # Hàm Rename Tối Ưu (Structural Rename):
    # Vì biến xp nằm ngay sau biến x (level chẵn/lẻ liên tiếp),
    # ta chỉ cần đổi level của node từ (2*i + 1) thành (2*i).
    memo_ren = {}

    def rename_xp_to_x(node):
        if node in (0, 1): return node
        if node in memo_ren: return memo_ren[node]

        lvl, low, high = bdd.nodes[node]
        var_name = bdd.level2var[lvl]

        if var_name.startswith("xp_"):
            # Biến xp -> Đổi thành x (level giảm 1)
            new_lvl = lvl - 1
            res = bdd._mk(new_lvl, rename_xp_to_x(low), rename_xp_to_x(high))
        else:
            # Biến x -> Giữ nguyên (nhưng đệ quy con)
            res = bdd._mk(lvl, rename_xp_to_x(low), rename_xp_to_x(high))

        memo_ren[node] = res
        return res

    # 4. Vòng lặp tìm kiếm
    while True:
        # a. Tìm trạng thái tiếp theo: Next = S(x) & R(x, x')
        temp = bdd.land(S, R)
        if temp == 0: break

        # b. Khử biến x: Exists x. (S & R) -> Hàm chỉ chứa xp
        img_xp = bdd.exists(temp, x_levels)

        # c. Đổi tên: xp -> x
        memo_ren.clear()
        S_next = rename_xp_to_x(img_xp)

        # d. Hợp nhất: S_new = S | S_next
        S_new = bdd.lor(S, S_next)

        if S_new == S: break
        S = S_new

    elapsed = time.perf_counter() - start_time
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    # Tính số trạng thái (Chỉ tính trên biến x, chia cho không gian biến xp)
    real_count = bdd.satcount(S, len(var_order)) // (2 ** num_places)
    return real_count, elapsed, peak_mem, S, bdd


# =============================================================
# PART 3: WRAPPER FOR REACHABILITY.PY (BFS/DFS)
# =============================================================

def run_explicit_wrapper(net: PetriNet, method: str):
    """Gọi hàm từ file reachability.py để đảm bảo tính nhất quán"""
    tracemalloc.start()
    start_time = time.perf_counter()

    if method == 'BFS':
        markings = reachable_markings_bfs(net)
    else:
        markings = reachable_markings_dfs(net)

    elapsed = time.perf_counter() - start_time
    _, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return len(markings), elapsed, peak_mem, markings


# =============================================================
# MAIN PROGRAM
# =============================================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 3 - Symbolic Reachability & Comparison")
    parser.add_argument("--model", type=str, default="../Standard PNMLs/DocAndPatientDeadlock.pnml.pnml")
    args = parser.parse_args()

    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

    if not os.path.exists(pnml_path):
        print(f"{Color.RED}❌ File not found: {pnml_path}{Color.RESET}")
        sys.exit(1)

    print(f"📂 Loading: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net: sys.exit(1)

    # --- 1. EXPLICIT BFS (Calling reachability.py) ---
    print(f"\n[1] Running EXPLICIT BFS approach (via reachability.py)")
    bfs_cnt, bfs_time, bfs_mem, bfs_list = run_explicit_wrapper(net, 'BFS')
    print(f"   -> Found: {bfs_cnt} markings")
    print(f"   -> Time:  {bfs_time:.6f}s")
    print(f"   -> Mem:   {bfs_mem} bytes")

    # --- 2. EXPLICIT DFS (Calling reachability.py) ---
    print(f"\n[2] Running EXPLICIT DFS approach (via reachability.py)")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = run_explicit_wrapper(net, 'DFS')
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    # --- 3. SYMBOLIC BDD (Pure Python) ---
    print(f"\n[3] Running SYMBOLIC BDD approach")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = run_symbolic_search_pure(net)
    print(f"   -> Found: {bdd_cnt} markings")
    print(f"   -> Time:  {bdd_time:.6f}s")
    print(f"   -> Mem:   {bdd_mem} bytes")

    # --- COMPARISON ---
    print("\n=== COMPARISON ===")
    if bfs_cnt == dfs_cnt == bdd_cnt:
        print(f"{Color.GREEN}✅ Result Match!{Color.RESET}")
    else:
        print(f"{Color.RED}❌ Result Mismatch! (BFS:{bfs_cnt}, DFS:{dfs_cnt}, BDD:{bdd_cnt}){Color.RESET}")

    bfs_t = bfs_time if bfs_time > 0 else 1e-9
    dfs_t = dfs_time if dfs_time > 0 else 1e-9

    print(f"Ratio (BDD vs BFS) is {bdd_time / bfs_t:.2f}")
    print(f"Ratio (BDD vs DFS) is {bdd_time / dfs_t:.2f}")

    # --- IN BDD FUNCTION DẠNG DỄ ĐỌC (DNF) ---
    print("\n" + "=" * 40)
    print(f"{Color.CYAN}--- SYMBOLIC BDD FUNCTION (DNF Form) ---{Color.RESET}")
    if bdd_cnt <= 1000:
        try:
            print(bdd_mgr.to_dnf_string(bdd_S))
        except Exception as e:
            print(f"(Error printing function: {e})")
    else:
        print(f"(Function too complex to print - {bdd_cnt} markings)")
    print("=" * 40)

    # --- IN DANH SÁCH MARKING CHI TIẾT (Từ BFS) ---
    print("\n--- [Explicit] Detailed Reachable Markings ---")
    limit_print = 50

    # Lấy thông tin để in đẹp từ reachability.py
    place_order, _ = build_place_index(net)
    groups = auto_group_places(net)

    for i, m in enumerate(bfs_list):
        if i >= limit_print:
            print(f"... and {len(bfs_list) - limit_print} more markings.")
            break
        print(f"M{i}:")
        # Sử dụng hàm in đẹp từ file reachability.py
        print(pretty_marking_vec(m, net, place_order, groups))
        print("-" * 30)