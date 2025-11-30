# =============================================================
# symbolic_computation_BDD.py (FINAL MEMORY FIX VERSION)
# Task 3: Symbolic Reachability + Comparison + Readable Logic
# =============================================================

import os
import time
import tracemalloc
import sys
import re
from collections import deque, defaultdict, Counter
from typing import List, Dict, Tuple, Set

# Tăng giới hạn đệ quy để in được công thức dài
sys.setrecursionlimit(50000)

# --- IMPORT MODULE ---
from parser import parse_pnml, PetriNet


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
# PART 1: EXPLICIT LOGIC (TASK 2 - BFS/DFS & PRETTY PRINT)
# =============================================================

def is_enabled(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> bool:
    if trans_id not in net.input_arcs: return False
    for place_id, weight in net.input_arcs[trans_id]:
        if marking.get(place_id, 0) < weight: return False
    return True


def fire_transition(net: PetriNet, trans_id: str, marking: Dict[str, int]) -> Dict[str, int]:
    new_marking = marking.copy()
    for place_id, weight in net.input_arcs.get(trans_id, []):
        new_marking[place_id] = max(0, new_marking.get(place_id, 0) - weight)
    for place_id, weight in net.output_arcs.get(trans_id, []):
        new_marking[place_id] = new_marking.get(place_id, 0) + weight
    return new_marking


def marking_to_tuple(marking: Dict[str, int], place_order: List[str]) -> Tuple[int]:
    return tuple(marking[p] for p in place_order)


def auto_group_places(net: PetriNet):
    """Gom nhóm tên Place để in output Task 2 cho gọn"""
    tokenized = {}
    prefix_count, suffix_count = Counter(), Counter()
    for pid, place in net.places.items():
        name = place.name
        parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+|[0-9]+", name)
        if not parts: parts = [name]
        tokenized[pid] = parts
        if len(parts) >= 2:
            prefix_count[parts[0]] += 1
            suffix_count[parts[-1]] += 1
    common_prefixes = {k for k, v in prefix_count.items() if v > 1}
    common_suffixes = {k for k, v in suffix_count.items() if v > 1}
    groups = defaultdict(list)
    for pid, parts in tokenized.items():
        if parts[0] in common_prefixes:
            groups[parts[0]].append(pid)
        elif parts[-1] in common_suffixes:
            groups[parts[-1]].append(pid)
        else:
            groups["Misc"].append(pid)
    return groups


def pretty_marking(marking: Dict[str, int], net: PetriNet) -> str:
    groups = auto_group_places(net)
    lines = []
    for gname in sorted(groups.keys(), key=lambda x: (x != "Misc", x)):
        pids = groups[gname]
        formatted = []
        for pid in pids:
            val = marking.get(pid, 0)
            color = Color.GREEN if val > 0 else Color.RED
            formatted.append(f"{net.places[pid].name}: {color}{val}{Color.RESET}")
        lines.append(f"   {gname}: " + " | ".join(formatted))
    return "\n".join(lines)


def run_explicit_search(net: PetriNet, mode='BFS'):
    """Chạy BFS/DFS để so sánh hiệu năng"""
    place_order = list(net.places.keys())
    initial = {pid: p.initial_marking for pid, p in net.places.items()}
    visited = set()
    visited.add(marking_to_tuple(initial, place_order))

    container = deque([initial]) if mode == 'BFS' else [initial]
    all_markings = [initial]

    tracemalloc.start()
    start_time = time.perf_counter()

    while container:
        current = container.popleft() if mode == 'BFS' else container.pop()
        for t_id in net.transitions:
            if is_enabled(net, t_id, current):
                new_m = fire_transition(net, t_id, current)
                tup = marking_to_tuple(new_m, place_order)
                if tup not in visited:
                    visited.add(tup)
                    container.append(new_m)
                    all_markings.append(new_m)

    elapsed = time.perf_counter() - start_time
    current_mem, peak_mem = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return len(all_markings), elapsed, peak_mem, all_markings


# =============================================================
# PART 2: SYMBOLIC BDD CLASS (TASK 3 - CUSTOM)
# =============================================================

class BDD:
    __slots__ = ("uniq", "ite_cache", "var2level", "level2var", "nodes")

    def __init__(self, var_order: List[str]):
        self.var2level = {name: i for i, name in enumerate(var_order)}
        self.level2var = {i: name for i, name in enumerate(var_order)}
        self.uniq = {}
        self.nodes = {}
        self.ite_cache = {}
        self.uniq[(None, 0, 0)] = 0
        self.uniq[(None, 1, 1)] = 1
        self.nodes[0] = (None, 0, 0)
        self.nodes[1] = (None, 1, 1)

    def const(self, val: bool) -> int:
        return 1 if val else 0

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
        if u in (0, 1): return None
        return self.nodes[u][0]

    def ite(self, i: int, t: int, e: int) -> int:
        if i == 1: return t
        if i == 0: return e
        if t == e: return t
        key = (i, t, e)
        if key in self.ite_cache: return self.ite_cache[key]
        top_i = self.top_level(i)
        top_t = self.top_level(t)
        top_e = self.top_level(e)
        lvls = [x for x in (top_i, top_t, top_e) if x is not None]
        if not lvls: return t if i == 1 else e
        top = min(lvls)
        i0, i1 = self.cof(i, top, 0), self.cof(i, top, 1)
        t0, t1 = self.cof(t, top, 0), self.cof(t, top, 1)
        e0, e1 = self.cof(e, top, 0), self.cof(e, top, 1)
        res = self._mk(top, self.ite(i0, t0, e0), self.ite(i1, t1, e1))
        self.ite_cache[key] = res
        return res

    def cof(self, u: int, target_lvl: int, val: int = 0) -> int:
        if u in (0, 1): return u
        lvl, low, high = self.nodes[u]
        if lvl > target_lvl: return u
        if lvl == target_lvl: return low if val == 0 else high
        return self._mk(lvl, self.cof(low, target_lvl, val), self.cof(high, target_lvl, val))

    def land(self, a: int, b: int) -> int:
        return self.ite(a, b, 0)

    def lor(self, a: int, b: int) -> int:
        return self.ite(a, 1, b)

    def lnot(self, a: int) -> int:
        return self.ite(a, 0, 1)

    def exists(self, u: int, var_names: List[str]) -> int:
        res = u
        for name in var_names:
            lvl = self.var2level[name]
            f0 = self.cof(res, lvl, 0)
            f1 = self.cof(res, lvl, 1)
            res = self.lor(f0, f1)
        return res

    def satcount(self, u: int, scope_vars: List[str]) -> int:
        scope_lvls = {self.var2level[v] for v in scope_vars}
        memo = {}

        def count(node):
            if node == 0: return 0
            if node == 1: return 1
            if node in memo: return memo[node]
            lvl, low, high = self.nodes[node]
            skip_low = self._count_skip(lvl, self.top_level(low), scope_lvls)
            skip_high = self._count_skip(lvl, self.top_level(high), scope_lvls)
            res = (pow(2, skip_low) * count(low)) + (pow(2, skip_high) * count(high))
            memo[node] = res
            return res

        root_lvl = self.top_level(u)
        return pow(2, self._count_skip(-1, root_lvl, scope_lvls)) * count(u)

    def _count_skip(self, current, next_l, scope):
        upper = next_l if next_l is not None else float('inf')
        return sum(1 for sl in scope if current < sl < upper)

    # --- HÀM IN CÔNG THỨC BDD "DỄ NHÌN" (DNF - Sum of Products) ---
    def to_dnf_string(self, u: int) -> str:
        """Xuất ra công thức dạng tuyển (A & B) | (C & D) ... dễ đọc hơn"""
        if u == 0: return "False"
        if u == 1: return "True"

        paths = []

        # Duyệt cây để tìm tất cả các đường dẫn đến node 1 (True)
        def collect_paths(node, current_path):
            if node == 0: return
            if node == 1:
                paths.append(current_path[:])
                return

            lvl, low, high = self.nodes[node]
            name = self.level2var[lvl]

            # Nhánh High (var=1)
            current_path.append(name)
            collect_paths(high, current_path)
            current_path.pop()

            # Nhánh Low (var=0)
            current_path.append(f"!{name}")
            collect_paths(low, current_path)
            current_path.pop()

        collect_paths(u, [])

        # Format string đẹp
        clauses = []
        for p in paths:
            clauses.append("(" + " & ".join(p) + ")")

        return " \n| ".join(clauses)


# =============================================================
# PART 3: SYMBOLIC REACHABILITY LOGIC
# =============================================================

def build_transition_relation_bdd(bdd: BDD, net: PetriNet, place_order: List[str], name_map: Dict):
    R = bdd.const(False)
    for t_id in net.transitions:
        pre = {pid for pid, w in net.input_arcs.get(t_id, [])}
        post = {pid for pid, w in net.output_arcs.get(t_id, [])}
        en = bdd.const(True)
        for p in pre: en = bdd.land(en, bdd.var(name_map[p][0]))
        for p in (post - pre): en = bdd.land(en, bdd.lnot(bdd.var(name_map[p][0])))
        upd = bdd.const(True)
        changed = pre.union(post)
        for p in (pre - post): upd = bdd.land(upd, bdd.lnot(bdd.var(name_map[p][1])))
        for p in post: upd = bdd.land(upd, bdd.var(name_map[p][1]))
        for p in place_order:
            if p not in changed:
                vx, vxp = bdd.var(name_map[p][0]), bdd.var(name_map[p][1])
                eq = bdd.lor(bdd.land(vx, vxp), bdd.land(bdd.lnot(vx), bdd.lnot(vxp)))
                upd = bdd.land(upd, eq)
        R = bdd.lor(R, bdd.land(en, upd))
    return R


def rename_Xp_to_X(bdd: BDD, u: int, name_map: Dict, place_order: List[str]) -> int:
    res = u
    for p in place_order:
        x, xp = name_map[p]
        xp_lvl = bdd.var2level[xp]
        xv = bdd.var(x)
        f1, f0 = bdd.cof(res, xp_lvl, 1), bdd.cof(res, xp_lvl, 0)
        res = bdd.lor(bdd.land(xv, f1), bdd.land(bdd.lnot(xv), f0))
    return res


def run_symbolic_search(net: PetriNet):
    place_order = sorted(list(net.places.keys()))
    X_vars = [f"x_{p}" for p in place_order]
    Xp_vars = [f"xp_{p}" for p in place_order]
    name_map = {p: (f"x_{p}", f"xp_{p}") for p in place_order}
    bdd = BDD(X_vars + Xp_vars)

    tracemalloc.start()  # Bắt đầu đo RAM
    start_time = time.perf_counter()

    S = bdd.const(True)
    for p in place_order:
        val = net.places[p].initial_marking
        bit = 1 if val > 0 else 0
        v = bdd.var(name_map[p][0])
        S = bdd.land(S, v) if bit else bdd.land(S, bdd.lnot(v))

    R = build_transition_relation_bdd(bdd, net, place_order, name_map)
    while True:
        temp = bdd.land(S, R)
        img_xp = bdd.exists(temp, X_vars)
        img_x = rename_Xp_to_X(bdd, img_xp, name_map, place_order)
        S_new = bdd.lor(S, img_x)
        if S_new == S: break
        S = S_new

    elapsed = time.perf_counter() - start_time
    current, peak_mem = tracemalloc.get_traced_memory()  # Lấy peak RAM
    tracemalloc.stop()  # Dừng đo

    count = bdd.satcount(S, X_vars)
    # Trả về peak_mem thay vì len(bdd.nodes)
    return int(count), elapsed, peak_mem, S, bdd


# =============================================================
# MAIN COMPARISON LOGIC
# =============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Task 3 - Symbolic Reachability & Comparison")
    parser.add_argument("--model", type=str, default="../Standard PNMLs/diningPhilosophers.pnml")
    args = parser.parse_args()

    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

    print(f"📂 Loading: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net: sys.exit(1)

    print("\n[1] Running EXPLICIT BFS approach")
    bfs_cnt, bfs_time, bfs_mem, bfs_list = run_explicit_search(net, 'BFS')
    print(f"   -> Found: {bfs_cnt} markings")
    print(f"   -> Time:  {bfs_time:.6f}s")
    print(f"   -> Mem:   {bfs_mem} bytes")

    print("\n[2] Running EXPLICIT DFS approach")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = run_explicit_search(net, 'DFS')
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    print("\n[3] Running SYMBOLIC BDD approach")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = run_symbolic_search(net)
    print(f"   -> Found: {bdd_cnt} markings")
    print(f"   -> Time:  {bdd_time:.6f}s")
    # In ra Memory (Bytes) cho đồng bộ
    print(f"   -> Mem:   {bdd_mem} bytes")

    print("\n=== COMPARISON ===")
    if bfs_cnt == dfs_cnt == bdd_cnt:
        print(f"{Color.GREEN}✅ Result Match!{Color.RESET}")
    else:
        print(f"{Color.RED}❌ Result Mismatch! (BFS:{bfs_cnt}, DFS:{dfs_cnt}, BDD:{bdd_cnt}){Color.RESET}")

    bfs_t = bfs_time if bfs_time > 0 else 1e-9
    dfs_t = dfs_time if dfs_time > 0 else 1e-9
    # Tính tỉ lệ ngược lại: Time BDD / Time BFS
    print(f"Ratio (BDD vs BFS) is {bdd_time / bfs_t:.2f}")
    print(f"Ratio (BDD vs DFS) is {bdd_time / dfs_t:.2f}")

    # --- IN BDD FUNCTION DẠNG DỄ ĐỌC ---
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

    print("\n--- [Explicit] Detailed Reachable Markings ---")
    limit_print = 50
    for i, m in enumerate(bfs_list):
        if i >= limit_print:
            print(f"... and {len(bfs_list) - limit_print} more markings.")
            break
        print(f"M{i}:")
        print(pretty_marking(m, net))
        print("-" * 30)