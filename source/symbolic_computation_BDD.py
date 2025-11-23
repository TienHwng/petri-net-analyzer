# =============================================================
# symbolic_computation_BDD.py
# Task 3 - Symbolic Reachability using Binary Decision Diagrams
# Author: Your Group - MM-251 Assignment (CO2011)
# =============================================================

import os
import time
import tracemalloc
from dd.autoref import BDD
from parser import parse_pnml, PetriNet


# =============================================================
# Helper functions for BDD-based symbolic computation
# =============================================================

def build_vars(bdd: BDD, place_order):
    """Declare BDD variables for current and next state (primed)."""
    curr = [f"{p}" for p in place_order]
    nxt = [f"{p}'" for p in place_order]
    bdd.declare(*curr, *nxt)
    return curr, nxt


def marking_to_bdd(bdd: BDD, place_order, marking):
    """Convert a marking (dict) into BDD formula."""
    f = bdd.true
    for p in place_order:
        v = bdd.var(p)
        if marking.get(p, 0) == 1:
            f = f & v
        else:
            f = f & ~v
    return f


def eq_var_pair(bdd: BDD, a: str, b: str):
    """Return BDD for (a <-> b)."""
    va, vb = bdd.var(a), bdd.var(b)
    return (va & vb) | (~va & ~vb)


def build_transition_relation(bdd: BDD, net: PetriNet, place_order):
    """Construct symbolic transition relation R(X, X')."""
    R = bdd.false
    for t_id, _ in net.transitions.items():
        # Enabled condition (current marking)
        pre = bdd.true
        for (p, w) in net.input_arcs.get(t_id, []):
            if w > 0:
                pre &= bdd.var(p)

        # Postcondition (next marking)
        post = bdd.true
        outputs = {p for (p, _) in net.output_arcs.get(t_id, [])}
        inputs = {p for (p, _) in net.input_arcs.get(t_id, [])}

        for p in place_order:
            pnext = f"{p}'"
            if p in outputs:
                post &= bdd.var(pnext)
            elif p in inputs and p not in outputs:
                post &= ~bdd.var(pnext)
            else:
                post &= eq_var_pair(bdd, p, pnext)

        R |= (pre & post)

    return R


def existential_quantify(bdd: BDD, f, vars_to_elim):
    """Existentially quantify (∃ vars_to_elim . f)."""
    return bdd.exist(vars_to_elim, f)


def rename_next_to_curr(bdd: BDD, f, place_order):
    """Rename next-state vars p' -> current vars p."""
    subs = {f"{p}'": bdd.var(p) for p in place_order}
    return f.let(subs)


# =============================================================
# Main symbolic reachability algorithm
# =============================================================

def symbolic_reachability(net: PetriNet):
    """Compute reachable markings using BDD fixed-point iteration."""
    place_order = list(net.places.keys())
    bdd = BDD()
    curr_vars, next_vars = build_vars(bdd, place_order)

    initial = {pid: net.places[pid].initial_marking for pid in place_order}
    Reach = marking_to_bdd(bdd, place_order, initial)
    R = build_transition_relation(bdd, net, place_order)

    print("\n=== SYMBOLIC REACHABILITY (BDD) ===")

    tracemalloc.start()
    start_time = time.perf_counter()

    old = bdd.false
    iteration = 0
    while Reach != old:
        iteration += 1
        old = Reach
        Temp = Reach & R
        Post_next = existential_quantify(bdd, Temp, curr_vars)
        Post = rename_next_to_curr(bdd, Post_next, place_order)
        Reach = Reach | Post

    elapsed = time.perf_counter() - start_time
    peak_mem = tracemalloc.get_traced_memory()[1] / (1024 * 1024)
    tracemalloc.stop()

    print(f"Iterations until fixpoint: {iteration}")
    print(f"BDD size (#nodes): {bdd.size(Reach)}")
    print(f"Elapsed time: {elapsed:.4f} s")
    print(f"Peak memory: {peak_mem:.2f} MB")

    # Try to count reachable markings (optional)
    try:
        count = bdd.count(Reach, nvars=len(place_order))
        print(f"Total reachable markings (estimated): {int(count)}")
    except Exception:
        print("BDD count() not available on this backend.")

    return Reach


# =============================================================
# Command-line interface
# =============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Task 3 - Symbolic Reachability Analysis using BDD"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="F:/MM-251-Assignment/Standard PNMLs/diningPhilosophers.pnml",
        help="Path to PNML model file",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    pnml_path = os.path.normpath(os.path.join(base_dir, args.model))

    print(f"📂 Loading PNML model: {pnml_path}")
    if not os.path.exists(pnml_path):
        print(f"❌ Error: File not found.")
        exit(1)

    net = parse_pnml(pnml_path)
    if not net:
        print(f"❌ Error parsing PNML file.")
        exit(1)

    Reach = symbolic_reachability(net)
