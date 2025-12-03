# =============================================================
# symbolic.py
# Task 3 – Symbolic reachability with BDDs (PyEDA version)
#   - Uses PyEDA BDDs to encode 1-safe Petri net markings
#   - Computes Reach(M0) symbolically and compares with explicit BFS/DFS
# =============================================================

import os
import sys
import time
from typing import Dict, List, Tuple, Any

from parser import PetriNet, parse_pnml
from reachability import (
    build_place_index,
    build_indexed_arcs,
    reachable_markings_bfs,
    reachable_markings_dfs,
    pretty_marking_vec,
    Color,
)

# PyEDA BDD primitives
from pyeda.boolalg.bdd import BDDZERO, BDDONE, bddvar, bdd2expr


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
# BDD encoding for a 1-safe Petri net (PyEDA)
# -------------------------------------------------------------
def build_bdd_encoding(
    net: PetriNet,
) -> Tuple[
    List[str],
    Dict[str, Any],
    Dict[str, Any],
    Any,
    Any,
    Dict[str, str],
]:
    """
    Xây dựng encoding BDD cho Petri net 1-safe.

    Returns
    -------
    place_order : List[str]
        Danh sách ID của các place theo thứ tự cố định.
    cur_vars : Dict[str, BDDVariable]
        pid -> biến BDD cho trạng thái hiện tại x_pid.
    next_vars : Dict[str, BDDVariable]
        pid -> biến BDD cho trạng thái kế tiếp x_pid_next.
    init : BDD
        BDD biểu diễn marking ban đầu I(x).
    trans_rel : BDD
        BDD biểu diễn quan hệ chuyển trạng thái T(x, x').
    var_to_place_name : Dict[str, str]
        Map "x_<pid>" -> tên place (dùng cho Task 4).
    """
    # Thứ tự place và map id -> index (giống Task 2)
    place_order, pid_to_index = build_place_index(net)

    # Xây dựng pre / post arcs dựa trên index (tái dùng từ Task 2)
    pre_arcs, post_arcs = build_indexed_arcs(net, pid_to_index)

    # Tạo biến BDD cho state hiện tại và state kế tiếp
    cur_vars: Dict[str, Any] = {}
    next_vars: Dict[str, Any] = {}
    var_to_place_name: Dict[str, str] = {}

    for pid in place_order:
        x = bddvar(f"x_{pid}")
        xp = bddvar(f"x_{pid}_next")
        cur_vars[pid] = x
        next_vars[pid] = xp
        var_to_place_name[f"x_{pid}"] = net.places[pid].name

    # Initial marking I(x)
    init = BDDONE
    for pid in place_order:
        x = cur_vars[pid]
        has_token = net.places[pid].initial_marking > 0
        init = init & x if has_token else init & ~x

    # Transition relation T(x, x') = OR_t T_t(x, x')
    trans_rel = BDDZERO

    for t_id in net.transitions.keys():
        # Giữ semantics từ explicit: transition không có input thì không enable
        if t_id not in pre_arcs:
            continue

        preset_idxs = {idx for idx, _w in pre_arcs.get(t_id, [])}
        postset_idxs = {idx for idx, _w in post_arcs.get(t_id, [])}

        # Enable condition: tất cả place trong preset phải có token
        enable = BDDONE
        for idx in preset_idxs:
            pid = place_order[idx]
            enable = enable & cur_vars[pid]

        # Update condition: quan hệ giữa x và x'
        update = BDDONE
        for idx, pid in enumerate(place_order):
            x = cur_vars[pid]
            xp = next_vars[pid]

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
                eq = (x & xp) | (~x & ~xp)

            update = update & eq

        t_rel = enable & update
        trans_rel = trans_rel | t_rel

    return place_order, cur_vars, next_vars, init, trans_rel, var_to_place_name


# -------------------------------------------------------------
# Symbolic reachability (Task 3 core)
# -------------------------------------------------------------
def symbolic_reachability(
    net: PetriNet,
) -> Tuple[Any, Dict[str, float], Dict[str, Any]]:
    """
    Task 3 – Tính tập reachable markings bằng BDD (PyEDA).

    Thuật toán:
      - Encode marking và transition relation bằng BDD.
      - Khởi tạo reached = I(x), frontier = I(x).
      - Lặp đến fixpoint:
            step(x, x')   = frontier(x) ∧ T(x, x')
            image'(x')    = ∃ x. step(x, x')         (smoothing trên biến x)
            image(x)      = rename x' -> x          (compose)
            new(x)        = image(x) ∧ ¬reached(x)
            reached(x)    = reached(x) ∨ new(x)
            frontier(x)   = new(x)
    """
    start = time.time()

    (
        place_order,
        cur_vars,
        next_vars,
        init,
        trans_rel,
        var_to_place_name,
    ) = build_bdd_encoding(net)

    cur_var_list = [cur_vars[pid] for pid in place_order]
    rename_map = {next_vars[pid]: cur_vars[pid] for pid in place_order}

    reached = init
    frontier = init

    # Vòng lặp fixpoint
    while True:
        # step(x, x') = frontier(x) ∧ T(x, x')
        step = frontier & trans_rel

        # image'(x') = ∃ x. step(x, x')
        image_prime = step.smoothing(cur_var_list)

        # image(x) = image'(x')[x' -> x]
        image = image_prime.compose(rename_map)

        # new(x) = image(x) \ reached(x)
        new_states = image & ~reached

        if new_states.is_zero():
            break

        reached = reached | new_states
        frontier = new_states

    duration = time.time() - start

    # Số marking reachable (model counting)
    num_markings = int(reached.satisfy_count())

    # Đếm số node BDD trong reachable set (duyệt DFS-preorder)
    node_ids = set()
    for node in reached.dfs_preorder():
        node_ids.add(id(node))
    num_nodes = len(node_ids)

    stats: Dict[str, float] = {
        "num_markings": float(num_markings),
        "num_nodes": float(num_nodes),
        "runtime_seconds": float(duration),
    }

    aux: Dict[str, Any] = {
        "place_order": place_order,
        "cur_vars": cur_vars,
        "next_vars": next_vars,
        "var_to_place_name": var_to_place_name,
    }

    return reached, stats, aux


# -------------------------------------------------------------
# Memory estimators (very rough, for comparison only)
# -------------------------------------------------------------
def estimate_memory_markings(markings: List[Tuple[int, ...]]) -> int:
    """
    Ước lượng dung lượng bộ nhớ (bytes) cho danh sách marking explicit.
    Không hoàn hảo nhưng đủ để so sánh tương đối với BDD.
    """
    total = sys.getsizeof(markings)
    for m in markings:
        total += sys.getsizeof(m)
        for v in m:
            total += sys.getsizeof(v)
    return total


def estimate_memory_bdd(reached_bdd: Any) -> int:
    """
    Ước lượng dung lượng bộ nhớ (bytes) cho reachable set BDD.
    Duyệt tất cả node trong DFS-preorder và cộng kích thước từng object.
    """
    seen = set()
    total = sys.getsizeof(reached_bdd)
    for node in reached_bdd.dfs_preorder():
        if id(node) in seen:
            continue
        seen.add(id(node))
        total += sys.getsizeof(node)
    return total


# -------------------------------------------------------------
# Small helper "manager" just for pretty-printing BDD as DNF
# -------------------------------------------------------------
class BDDManager:
    """
    Manager đơn giản để phù hợp với API run_symbolic_search:
      - to_dnf_string(bdd) -> str
    """

    @staticmethod
    def to_dnf_string(bdd: Any) -> str:
        """
        Convert BDD -> Expression (two-level SOP) -> string.
        Đây chính là một dạng DNF (sum-of-products).
        """
        expr = bdd2expr(bdd)  # conj=False (SOP) theo docs
        return str(expr)


# -------------------------------------------------------------
# Adapters that match your snippet API
# -------------------------------------------------------------
def run_explicit_search(
    net: PetriNet,
    method: str = "BFS",
) -> Tuple[int, float, int, List[Tuple[int, ...]]]:
    """
    Chạy BFS/DFS explicit reachability giống Task 2 và trả về:
        (count, runtime_seconds, memory_bytes, markings_list)
    """
    method_up = method.upper()
    start = time.time()

    if method_up == "BFS":
        markings = reachable_markings_bfs(net)
    elif method_up == "DFS":
        markings = reachable_markings_dfs(net)
    else:
        raise ValueError(f"Unknown method: {method}")

    duration = time.time() - start
    mem_bytes = estimate_memory_markings(markings)
    return len(markings), duration, mem_bytes, markings


def run_symbolic_search(
    net: PetriNet,
) -> Tuple[int, float, int, Any, BDDManager]:
    """
    Chạy symbolic Task 3 (BDD với PyEDA) và trả về:
        (count, runtime_seconds, memory_bytes, reached_bdd, bdd_manager)
    để khớp với đoạn code main bạn đưa.
    """
    reached, stats, aux = symbolic_reachability(net)
    bdd_cnt = int(stats["num_markings"])
    bdd_time = float(stats["runtime_seconds"])
    bdd_mem = estimate_memory_bdd(reached)
    mgr = BDDManager()
    return bdd_cnt, bdd_time, bdd_mem, reached, mgr


# -------------------------------------------------------------
# CLI main – đẹp như snippet của bạn
# -------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Task 3 - Symbolic Reachability & Comparison (PyEDA BDD)"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="../Standard PNMLs/file2_token_ring_1safe.pnml",
        help="Đường dẫn tới file PNML",
    )
    args = parser.parse_args()

    # Chuẩn hoá đường dẫn giống snippet
    pnml_path = os.path.normpath(args.model)
    if not os.path.exists(pnml_path):
        base_dir = os.path.dirname(os.path.abspath(__file__))
        pnml_path = os.path.join(base_dir, args.model)

    print(f"📂 Loading: {pnml_path}")
    net = parse_pnml(pnml_path)
    if not net:
        sys.exit(1)

    # 1) Explicit BFS
    print("\n[1] Running EXPLICIT BFS approach")
    bfs_cnt, bfs_time, bfs_mem, bfs_list = run_explicit_search(net, "BFS")
    print(f"   -> Found: {bfs_cnt} markings")
    print(f"   -> Time:  {bfs_time:.6f}s")
    print(f"   -> Mem:   {bfs_mem} bytes")

    # 2) Explicit DFS
    print("\n[2] Running EXPLICIT DFS approach")
    dfs_cnt, dfs_time, dfs_mem, dfs_list = run_explicit_search(net, "DFS")
    print(f"   -> Found: {dfs_cnt} markings")
    print(f"   -> Time:  {dfs_time:.6f}s")
    print(f"   -> Mem:   {dfs_mem} bytes")

    # 3) Symbolic BDD (PyEDA)
    print("\n[3] Running SYMBOLIC BDD approach (PyEDA)")
    bdd_cnt, bdd_time, bdd_mem, bdd_S, bdd_mgr = run_symbolic_search(net)
    print(f"   -> Found: {bdd_cnt} markings")
    print(f"   -> Time:  {bdd_time:.6f}s")
    print(f"   -> Mem:   {bdd_mem} bytes")

    # So sánh kết quả
    print("\n=== COMPARISON ===")
    if bfs_cnt == dfs_cnt == bdd_cnt:
        print(f"{Color.GREEN}✅ Result Match!{Color.RESET}")
    else:
        print(
            f"{Color.RED}❌ Result Mismatch! "
            f"(BFS:{bfs_cnt}, DFS:{dfs_cnt}, BDD:{bdd_cnt}){Color.RESET}"
        )

    bfs_t = bfs_time if bfs_time > 0 else 1e-9
    dfs_t = dfs_time if dfs_time > 0 else 1e-9
    print(f"Ratio (BDD vs BFS) is {bdd_time / bfs_t:.2f}")
    print(f"Ratio (BDD vs DFS) is {bdd_time / dfs_t:.2f}")

    # In BDD function dạng DNF nếu không quá lớn
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

    # # In một số marking explicit để đối chiếu
    # print("\n--- [Explicit] Detailed Reachable Markings (BFS) ---")
    # limit_print = 50
    # for i, m in enumerate(bfs_list):
    #     if i >= limit_print:
    #         print(f"... and {len(bfs_list) - limit_print} more markings.")
    #         break
    #     print(f"M{i}:")
    #     print(pretty_marking(m, net))
    #     print("-" * 30)