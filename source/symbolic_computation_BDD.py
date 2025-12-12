# =============================================================
# symbolic.py
# Task 3 – Symbolic reachability with BDDs (dd library version)
#   - Uses 'dd' (autoref) to encode 1-safe Petri net markings
#   - Computes Reach(M0) symbolically and compares with explicit BFS/DFS
# =============================================================

import os
import sys
import time
import argparse
from typing import Dict, List, Tuple, Any

sys.setrecursionlimit(50000)
# Import thư viện dd
try:
    from dd.autoref import BDD
except ImportError:
    print("Error: Library 'dd' not found. Please install it: pip install dd")
    sys.exit(1)

from parser import PetriNet, parse_pnml
from reachability import (
    build_place_index,
    build_indexed_arcs,
    reachable_markings_bfs,
    reachable_markings_dfs,
    pretty_marking_vec,
    auto_group_places,
    Color,
)


# -------------------------------------------------------------
# Helper: pretty-print a single explicit marking (wrapper)
# -------------------------------------------------------------
def pretty_marking(marking: Tuple[int, ...], net: PetriNet) -> str:
    """
    Thin wrapper around reachability.pretty_marking_vec so that we can call:
        pretty_marking(m, net)
    without passing place_order/groups manually.
    """
    place_order, _ = build_place_index(net)
    return pretty_marking_vec(marking, net, place_order)


# -------------------------------------------------------------
# BDD encoding for a 1-safe Petri net (Using dd)
# -------------------------------------------------------------
def build_bdd_encoding(
        net: PetriNet,
) -> Tuple[
    Any,  # bdd manager
    List[str],  # place_order
    List[str],  # cur_vars names
    List[str],  # next_vars names
    Any,  # init node
    Any,  # trans_rel node
    Dict[str, str]  # var_to_place_name
]:
    """
    Xây dựng encoding BDD cho Petri net 1-safe sử dụng thư viện `dd`.
    """
    # 1. Khởi tạo BDD Manager
    bdd = BDD()

    # Thứ tự place và map id -> index
    place_order, pid_to_index = build_place_index(net)

    # Xây dựng pre / post arcs dựa trên index
    pre_arcs, post_arcs = build_indexed_arcs(net, pid_to_index)

    # 2. Khai báo biến (Interleaved ordering thường tốt cho BDD)
    # x_0, x_0', x_1, x_1', ...
    cur_vars = []
    next_vars = []
    var_to_place_name = {}

    for pid in place_order:
        curr_v = f"x_{pid}"
        next_v = f"x_{pid}_next"

        bdd.declare(curr_v)
        bdd.declare(next_v)

        cur_vars.append(curr_v)
        next_vars.append(next_v)
        var_to_place_name[curr_v] = net.places[pid].name

    # 3. Initial marking I(x)
    # Trong dd, True là bdd.true, False là bdd.false
    init = bdd.true
    for i, pid in enumerate(place_order):
        var_name = cur_vars[i]
        has_token = net.places[pid].initial_marking > 0

        # Tạo node biến: bdd.var(name)
        var_node = bdd.var(var_name)

        if has_token:
            init = init & var_node
        else:
            init = init & ~var_node

    # 4. Transition relation T(x, x') = OR_t T_t(x, x')
    trans_rel = bdd.false

    for t_id in net.transitions.keys():
        # Transition không có input thì bỏ qua (theo logic explicit cũ)
        if t_id not in pre_arcs:
            continue

        preset_idxs = {idx for idx, _w in pre_arcs.get(t_id, [])}
        postset_idxs = {idx for idx, _w in post_arcs.get(t_id, [])}

        # Enable condition: tất cả place trong preset phải có token
        enable = bdd.true
        for idx in preset_idxs:
            pid = place_order[idx]
            # AND với x_pid
            enable = enable & bdd.var(cur_vars[idx])

        # Update condition: quan hệ giữa x và x'
        update = bdd.true
        for idx, pid in enumerate(place_order):
            x = bdd.var(cur_vars[idx])
            xp = bdd.var(next_vars[idx])

            in_preset = idx in preset_idxs
            in_postset = idx in postset_idxs

            if in_preset and not in_postset:
                # Token bị remove -> x'_p = 0
                eq = ~xp
            elif (not in_preset) and in_postset:
                # Token được add -> x'_p = 1
                eq = xp
            else:
                # Giữ nguyên / self-loop: x' <-> x
                # (x & xp) | (~x & ~xp)
                eq = (x & xp) | (~x & ~xp)

            update = update & eq

        # T_t = enable & update
        t_rel = enable & update

        # T = T | T_t
        trans_rel = trans_rel | t_rel

    return bdd, place_order, cur_vars, next_vars, init, trans_rel, var_to_place_name


# -------------------------------------------------------------
# Symbolic reachability (Task 3 core) - DD Version
# -------------------------------------------------------------
def symbolic_reachability(
        net: PetriNet,
) -> Tuple[Any, Any, Dict[str, float], Dict[str, Any]]:
    """
    Task 3 – Tính tập reachable markings bằng BDD (`dd`).
    """
    start = time.perf_counter()

    (
        bdd,
        place_order,
        cur_vars_names,
        next_vars_names,
        init,
        trans_rel,
        var_to_place_name,
    ) = build_bdd_encoding(net)

    # Map dùng để rename: { 'x_next': 'x' }
    # Lưu ý: trong dd.let, ta map biến cần thay thế -> biểu thức thay thế
    # Ta muốn đổi x' thành x. Tức là gán giá trị của x vào x'.
    # Tuy nhiên, image_prime chỉ chứa x'. Ta muốn biến nó thành công thức chứa x.
    # Trong `dd`, `let` thay thế biến bằng expression.
    # Cú pháp: { 'var_name_in_expr': bdd.var('new_var_name') }
    rename_map = {
        nx: bdd.var(curr)
        for nx, curr in zip(next_vars_names, cur_vars_names)
    }

    # Tập biến cần khử (x)
    qvars = set(cur_vars_names)

    reached = init
    frontier = init

    # Vòng lặp fixpoint
    while True:
        # 1. step(x, x') = frontier(x) ∧ T(x, x')
        step = frontier & trans_rel

        # 2. image'(x') = ∃ x. step(x, x')
        # exist trong `dd` nhận 1 list/set tên biến
        image_prime = bdd.exist(qvars, step)

        # 3. image(x) = image'(x')[x' -> x]
        # Sử dụng `let` để rename
        image = bdd.let(rename_map, image_prime)

        # 4. new(x) = image(x) \ reached(x)
        new_states = image & ~reached

        # Kiểm tra rỗng: so sánh với bdd.false
        if new_states == bdd.false:
            break

        reached = reached | new_states
        frontier = new_states

    duration = time.perf_counter() - start

    # Số marking reachable
    # count() đếm số assignment thỏa mãn.
    # Lưu ý: bdd.count() đếm trên tất cả các biến đã khai báo trong manager.
    # Chúng ta chỉ quan tâm đến các biến hiện tại (cur_vars).
    # Tuy nhiên, reached chỉ phụ thuộc vào cur_vars, nên các biến next_vars là "don't care".
    # Số nghiệm thực = bdd.count(reached) / (2 ^ số_biến_next)

    total_assignments = reached.count(nvars=len(cur_vars_names) + len(next_vars_names))
    # Chia cho không gian của biến next (vì chúng không xuất hiện trong reached)
    num_markings = total_assignments // (2 ** len(next_vars_names))

    # Số node BDD (len(bdd) trả về tổng số node trong manager, không phải của riêng hàm reached)
    # Để đếm node của riêng 'reached', ta dùng len(bdd.collect_garbage()) hoặc ước lượng.
    # Đơn giản nhất trong `dd`: kích thước DAG của node.
    num_nodes = len(bdd)  # Đây là tổng node trong manager (ước lượng sơ bộ)

    stats: Dict[str, float] = {
        "num_markings": float(num_markings),
        "num_nodes": float(num_nodes),
        "runtime_seconds": float(duration),
    }

    aux: Dict[str, Any] = {
        "place_order": place_order,
        "cur_vars": cur_vars_names,
        "next_vars": next_vars_names,
        "var_to_place_name": var_to_place_name,
        "trans_rel": trans_rel,
    }

    # Trả về cả object bdd manager để dùng sau này
    return bdd, reached, stats, aux


# -------------------------------------------------------------
# Memory estimators
# -------------------------------------------------------------
def estimate_memory_markings(markings: List[Tuple[int, ...]]) -> int:
    total = sys.getsizeof(markings)
    for m in markings:
        total += sys.getsizeof(m)
        for v in m:
            total += sys.getsizeof(v)
    return total


def estimate_memory_bdd(bdd_manager: Any) -> int:
    """
    Ước lượng bộ nhớ của BDD Manager `dd`.
    Không chính xác tuyệt đối, nhưng `dd` quản lý node tập trung.
    """
    # sys.getsizeof của manager + số lượng node * kích thước trung bình node
    # Đây chỉ là con số tương đối.
    return sys.getsizeof(bdd_manager) + len(bdd_manager) * 24


# -------------------------------------------------------------
# Helper Class for BDD Management (Interface Adapter)
# -------------------------------------------------------------
class BDDManagerAdapter:
    def __init__(self, bdd_instance, var_name_map=None):
        self.bdd = bdd_instance
        # Map: 'x_p1' -> 'Phil1_Thinking'
        self.var_name_map = var_name_map if var_name_map is not None else {}

    def to_dnf_string(self, u: Any) -> str:
        """
        Chuyển đổi node BDD 'u' sang dạng DNF với tên Place thực tế.
        Dạng: (Fork1 & Phil1_Thinking) | (~Fork1 & Phil1_Eating) ...
        """
        if u == self.bdd.false:
            return "FALSE"
        if u == self.bdd.true:
            return "TRUE"

        clauses = []
        
        # pick_iter trả về danh sách các biến
        for assignment in self.bdd.pick_iter(u):
            # Sắp xếp theo tên biến gốc (x_p1, x_p2...) để giữ thứ tự nhất quán
            sorted_vars = sorted(assignment.keys(), key=lambda x: (len(x), x))
            
            literals = []
            for var_code in sorted_vars:
                val = assignment[var_code]
                
                # Lấy tên thật từ map, nếu không có thì dùng tên biến (x_p...)
                real_name = self.var_name_map.get(var_code, var_code)
                
                if val:
                    literals.append(real_name)          # Ví dụ: Fork1
                else:
                    literals.append(f"~{real_name}")    # Ví dụ: ~Fork1
            
            # Tạo chuỗi cho 1 marking
            clause_str = "(" + " & ".join(literals) + ")"
            clauses.append(clause_str)

        # Nối các marking lại
        return "\n| ".join(clauses)

    def land(self, u, v): return u & v
    def lor(self, u, v): return u | v
    def lnot(self, u): return ~u
    def var(self, name): return self.bdd.var(name)


# -------------------------------------------------------------
# Adapters that match your snippet API
# -------------------------------------------------------------
def run_explicit_search(
        net: PetriNet,
        method: str = "BFS",
) -> Tuple[int, float, int, List[Tuple[int, ...]]]:
    method_up = method.upper()
    start = time.perf_counter()

    if method_up == "BFS":
        markings = reachable_markings_bfs(net)
    elif method_up == "DFS":
        markings = reachable_markings_dfs(net)
    else:
        raise ValueError(f"Unknown method: {method}")

    duration = time.perf_counter() - start
    mem_bytes = estimate_memory_markings(markings)
    return len(markings), duration, mem_bytes, markings


def run_symbolic_search(
        net: PetriNet,
) -> Tuple[int, float, int, Any, BDDManagerAdapter]:
    """
    Chạy symbolic Task 3 (BDD với dd) và trả về interface tương thích.
    """
    bdd_manager, reached_node, stats, aux = symbolic_reachability(net)

    bdd_cnt = int(stats["num_markings"])
    bdd_time = float(stats["runtime_seconds"])
    bdd_mem = estimate_memory_bdd(bdd_manager)

    # Lấy map tên biến -> tên place thực tế
    var_map = aux.get("var_to_place_name", {})

    # TRUYỀN var_map VÀO ĐÂY
    mgr = BDDManagerAdapter(bdd_manager, var_map)

    return bdd_cnt, bdd_time, bdd_mem, reached_node, mgr


# -------------------------------------------------------------
# CLI main
# -------------------------------------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Task 3 - Symbolic Reachability & Comparison (dd Library)")
    parser.add_argument("--model", type=str, default="../Standard PNMLs/philo.pnml")
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

    # --- 1. EXPLICIT BFS ---
    print(f"\n[1] Running EXPLICIT BFS approach")
    bfs_cnt, bfs_time, bfs_mem, bfs_list = run_explicit_search(net, 'BFS')
    print(f"   -> Found: {bfs_cnt} markings")
    print(f"   -> Time:  {bfs_time:.6f}s")
    print(f"   -> Mem:   {bfs_mem} bytes")

    # --- 2. EXPLICIT DFS ---
    print(f"\n[2] Running EXPLICIT DFS approach")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = run_explicit_search(net, 'DFS')
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    # --- 3. SYMBOLIC BDD (dd library) ---
    print(f"\n[3] Running SYMBOLIC BDD approach (dd library)")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = run_symbolic_search(net)
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

    # --- IN BDD FUNCTION DẠNG DỄ ĐỌC ---
    print("\n" + "=" * 40)
    print(f"{Color.CYAN}--- SYMBOLIC BDD FUNCTION ---{Color.RESET}")
    if bdd_cnt <= 50:
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