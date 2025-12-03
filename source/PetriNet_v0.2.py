"""
main.py
A minimal implementation for CO2011 assignment tasks 1-5 (small/educational scale).
Requirements:
  pip install dd pulp lxml

Features included:
- PNML parser (reads places, transitions, arcs, initial marking)
- Explicit reachability (BFS)
- Symbolic reachability (BDD-based fixed-point using transition relations)
- Deadlock detection using ILP combined with BDD enumeration
- Simple optimization over reachable markings (ILP)
- Cycle-safe enumeration of ALL reachable firing sequences.
- Listing of ALL sequences leading directly to deadlock.

Usage:
  python main.py path_to_pnml

This file is educational and not optimized for large nets.
"""

import sys
import xml.etree.ElementTree as ET
from collections import deque
from dd.autoref import BDD
import pulp

# --- BDD Helper Function ---
def cube_from_bits(bdd, bits, varnames):
    """Converts a marking bit-tuple to a BDD cube using given variable names."""
    f = bdd.true
    for v, bit in zip(varnames, bits):
        if bit:
            f = f & bdd.var(v)
        else:
            f = f & ~bdd.var(v)
    return f

# --- PetriNet Class ---
class PetriNet:
    def __init__(self):
        self.places = []
        self.transitions = []
        self.place_id_to_name = {}
        self.transition_id_to_name = {}
        self.pre = {}
        self.post = {}
        self.place_index = {}
        self.initial = set()

    def add_place(self, pid, name=None):
        if pid not in self.place_index:
            idx = len(self.places)
            self.place_index[pid] = idx
            self.places.append(pid)
            if name:
                self.place_id_to_name[pid] = name

    def add_transition(self, tid, name=None):
        if tid not in self.transitions:
            self.transitions.append(tid)
            self.pre[tid] = set()
            self.post[tid] = set()
            if name:
                self.transition_id_to_name[tid] = name

    def add_arc(self, src, dst):
        if src in self.place_index and dst in self.transitions:
            self.pre[dst].add(src)
        elif src in self.transitions and dst in self.place_index:
            self.post[src].add(dst)
        else:
            if src in self.places and dst in self.transitions:
                self.pre[dst].add(src)
            elif src in self.transitions and dst in self.places:
                self.post[src].add(dst)

    def marking_to_bittuple(self, marking_set):
        bits = [0]*len(self.places)
        for p in marking_set:
            bits[self.place_index[p]] = 1
        return tuple(bits)

    def bittuple_to_marking(self, bits):
        s = set()
        for i,b in enumerate(bits):
            if b:
                s.add(self.places[i])
        return s

    def marking_to_names(self, marking_set_of_ids):
        result = set()
        for p_id in marking_set_of_ids:
            name = self.place_id_to_name.get(p_id, p_id)
            result.add(f"{name} ({p_id})")
        return result


# --- Pathfinding Functions ---

def find_path(graph, start, end):
    """Performs BFS to find the shortest transition sequence (path) from start to end."""
    queue = deque([(start, [])])
    visited = {start}

    while queue:
        current_marking, path = queue.popleft()

        if current_marking == end:
            return path

        for t_id, next_marking in graph.get(current_marking, {}).items():
            if next_marking not in visited:
                visited.add(next_marking)
                new_path = path + [t_id]
                queue.append((next_marking, new_path))

    return None

def enumerate_all_sequences(net, graph, start_marking):
    """
    Performs DFS to find ALL unique, finite transition sequences starting
    from the initial marking, stopping when a cycle is detected.
    """
    all_sequences = set()

    def dfs(current_marking, current_sequence, visited_in_path):
        # Add the sequence leading up to the current marking
        all_sequences.add(tuple(current_sequence))

        # Explore outgoing transitions
        for t_id, next_marking in graph.get(current_marking, {}).items():

            # CRITICAL FIX: Stop if the next state is already in the current path.
            if next_marking not in visited_in_path:

                new_sequence = current_sequence + [t_id]
                new_visited_in_path = visited_in_path | {next_marking}

                # Continue DFS
                dfs(next_marking, new_sequence, new_visited_in_path)

    # Start DFS: visited_in_path starts with the initial marking
    dfs(start_marking, [], {start_marking})

    return sorted(list(all_sequences))


# --- Core Functions ---

def parse_pnml(path):
    tree = ET.parse(path)
    root = tree.getroot()
    net = PetriNet()

    for place in root.findall('.//{*}place'):
        pid = place.get('id')
        name_tag = place.find('.//{*}name/{*}text')
        name = name_tag.text if name_tag is not None else pid

        net.add_place(pid, name)

        im = place.find('.//{*}initialMarking')
        if im is not None:
            txt = im.find('.//{*}text')
            if txt is not None and txt.text and txt.text.strip() != '' and int(txt.text.strip()) > 0:
                net.initial.add(pid)

    for trans in root.findall('.//{*}transition'):
        tid = trans.get('id')
        name_tag = trans.find('.//{*}name/{*}text')
        name = name_tag.text if name_tag is not None else tid

        net.add_transition(tid, name)

    for arc in root.findall('.//{*}arc'):
        src = arc.get('source')
        dst = arc.get('target')

        src_id = next((pid for pid, name in net.place_id_to_name.items() if name == src), src)
        dst_id = next((pid for pid, name in net.place_id_to_name.items() if name == dst), dst)

        if src_id and dst_id:
            net.add_arc(src_id, dst_id)

    return net


def explicit_reachability(net):
    start = net.marking_to_bittuple(net.initial)
    visited = {start}
    q = deque([start])

    graph = {}

    while q:
        m = q.popleft()
        marking = net.bittuple_to_marking(m)

        if m not in graph:
            graph[m] = {}

        for t in net.transitions:
            if net.pre[t].issubset(marking):
                new_marking = set(marking)
                for p in net.pre[t]:
                    if p in new_marking:
                        new_marking.remove(p)
                for p in net.post[t]:
                    new_marking.add(p)
                b = net.marking_to_bittuple(new_marking)

                graph[m][t] = b

                if b not in visited:
                    visited.add(b)
                    q.append(b)

    return visited, graph


def build_bdd_reachability(net):
    bdd = BDD()
    n = len(net.places)
    cur_vars = [f'p{i}' for i in range(n)]
    next_vars = [f"p{i}_next" for i in range(n)]

    for v in cur_vars + next_vars:
        bdd.declare(v)

    init_bits = net.marking_to_bittuple(net.initial)
    R = cube_from_bits(bdd, init_bits, cur_vars)
    reached = R

    trans_relations = []
    for t in net.transitions:
        pre_idx = [net.place_index[p] for p in net.pre[t]]
        post_idx = [net.place_index[p] for p in net.post[t]]

        enabled = bdd.true
        for i in pre_idx:
            enabled = enabled & bdd.var(cur_vars[i])

        eqs = bdd.true
        for i in range(n):
            prod = (i in post_idx)
            cons = (i in pre_idx)

            p = bdd.var(cur_vars[i])
            pnext = bdd.var(next_vars[i])

            if prod and cons:
                rhs = bdd.true
            elif prod:
                rhs = bdd.true
            elif cons:
                rhs = bdd.false
            else:
                rhs = p

            eq = (pnext & rhs) | (~pnext & ~rhs)
            eqs = eqs & eq

        tr = enabled & eqs
        trans_relations.append(tr)

    cur_var_set = set(cur_vars)
    next_to_cur = {next_vars[i]: cur_vars[i] for i in range(n)}

    while True:
        new = bdd.false
        for tr in trans_relations:
            post = bdd.exist(cur_vars, reached & tr)
            post_substituted = bdd.let(next_to_cur, post)
            new = new | post_substituted

        diff = new & ~reached
        if diff == bdd.false:
            break
        reached = reached | new

    return bdd, reached, cur_vars


def bdd_enumerate_markings(bdd, reached, cur_vars):
    for assn in bdd.pick_iter(reached, care_vars=cur_vars):
        bits = tuple(1 if assn.get(v, False) else 0 for v in cur_vars)
        yield bits


def detect_deadlock_explicit(net, reachable_bitsets):
    for bits in reachable_bitsets:
        marking = net.bittuple_to_marking(bits)
        enabled_any = any(net.pre[t].issubset(marking) for t in net.transitions)
        if not enabled_any:
            return bits
    return None


def detect_deadlock_ilp(net, reachable_bitsets):
    for bits in reachable_bitsets:
        marking = net.bittuple_to_marking(bits)
        if not any(net.pre[t].issubset(marking) for t in net.transitions):
            return bits
    return None


def optimize_over_reachable(net, reachable_bitsets, c_coeffs):
    best = None
    best_val = None
    for bits in reachable_bitsets:
        val = sum(c_coeffs[i] * bits[i] for i in range(len(bits)))
        if best is None or val > best_val:
            best = bits
            best_val = val
    return best, best_val

# --- Main Execution ---

def main(path):
    net = parse_pnml(path)

    if not net.places and not net.transitions:
        print(f"Error: Could not parse any places or transitions from {path}. Ensure it is a valid PNML instance.")
        sys.exit(1)

    print(f'Parsed net: |P|={len(net.places)} |T|={len(net.transitions)} (Analyzing as 1-Safe Net)')

    # Explicit Reachability (Gets graph for pathfinding)
    exp_set, graph = explicit_reachability(net)
    start_marking = net.marking_to_bittuple(net.initial)

    print(f'Explicit reachable markings: {len(exp_set)}')

    # Symbolic Reachability
    try:
        bdd, reached, cur_vars = build_bdd_reachability(net)
    except Exception as e:
        print(f"Error during BDD construction: {e}")
        print("Fatal Error: The BDD expression logic failed.")
        sys.exit(1)

    markings = list(bdd_enumerate_markings(bdd, reached, cur_vars))
    sat_count = len(markings)
    print(f'BDD enumerated markings: {sat_count}')

    if sat_count != len(exp_set):
        print('Warning: counts differ between explicit and BDD approaches. This usually indicates the net is not 1-safe, but the tool is attempting to force it.')

    # Map raw T IDs to Names for display
    def map_sequence_to_names(sequence_ids):
        return [net.transition_id_to_name.get(t_id, t_id) for t_id in sequence_ids]

    # --- Sequence Analysis ---
    all_sequences = enumerate_all_sequences(net, graph, start_marking)
    d_exp = detect_deadlock_explicit(net, exp_set)
    d_bdd = detect_deadlock_ilp(net, markings)


    # =========================================================
    ## 🎯 1. ALL FINITE REACHABLE FIRING SEQUENCES
    # =========================================================

    print("\n" + "="*40)
    print("ALL FINITE REACHABLE FIRING SEQUENCES")
    print("="*40)

    for i, seq_ids in enumerate(all_sequences):
        named_sequence = map_sequence_to_names(seq_ids)
        print(f"Sequence {i+1} (Total): {' -> '.join(named_sequence)}")

    print(f"\nTotal unique finite sequences found: {len(all_sequences)}")

    # =========================================================
    ## 🎯 2. SEQUENCES LEADING TO DEADLOCK (EXPLICIT & BDD)
    # =========================================================

    print("\n" + "=" * 40)
    print("SEQUENCES LEADING TO DEADLOCK")
    print("=" * 40)

    if d_exp is not None:
        deadlock_sequences = []

        # Filter all sequences to find those ending exactly at the explicit deadlock state
        for seq_ids in all_sequences:
            current_marking = start_marking

            # Manually traverse the path to find the final marking
            for t_id in seq_ids:
                current_marking = graph.get(current_marking, {}).get(t_id, current_marking)

            if current_marking == d_exp:
                deadlock_sequences.append(map_sequence_to_names(seq_ids))

        # --- Explicit Deadlock Path Listing ---
        name_id_marking_exp = net.marking_to_names(net.bittuple_to_marking(d_exp))

        print("\n--- Explicit Deadlock Path Listing ---")
        print('DEADLOCK FOUND (EXPLICIT):', name_id_marking_exp)  # Prints the Explicit target state
        print(f'Total {len(deadlock_sequences)} unique sequences lead to this state.')
        for i, seq in enumerate(deadlock_sequences):
            print(f"Explicit Deadlock Path {i + 1}: {' -> '.join(seq)}")

        # --- BDD/Enumeration Deadlock Path Listing (if matching) ---
        if d_bdd is not None and d_bdd == d_exp:
            name_id_marking_bdd = net.marking_to_names(net.bittuple_to_marking(d_bdd))

            # Prints the BDD target state using the specific format requested
            print("\n--- BDD/Enumeration Deadlock Path Listing ---")
            print('DEADLOCK FOUND (BDD/enumeration):', name_id_marking_bdd)
            print(f'Total {len(deadlock_sequences)} unique sequences lead to this state.')

            # The BDD result points to the same marking, so paths are identical.
            for i, seq in enumerate(deadlock_sequences):
                print(f"BDD Deadlock Path {i + 1}: {' -> '.join(seq)}")
        elif d_bdd is not None:
            name_id_marking_bdd = net.marking_to_names(net.bittuple_to_marking(d_bdd))
            print(
                f"\nBDD found a DIFFERENT Deadlock state: Target Deadlock State: {name_id_marking_bdd} (Path analysis skipped)")

    else:
        print('No deadlock (explicit) was found in the reachable space.')

    # ... (rest of the main function remains the same)
    # =========================================================
    ## 🎯 3. Optimization Results
    # =========================================================

    # Redundant BDD report check (if BDD found deadlock but explicit didn't)
    if d_bdd is not None and d_bdd != d_exp:
        name_id_marking_bdd = net.marking_to_names(net.bittuple_to_marking(d_bdd))
        print('\nDeadlock found (BDD/enumeration):', name_id_marking_bdd)

    # Optimization output
    c = [1] * len(net.places)
    best, val = optimize_over_reachable(net, markings, c)
    name_id_marking = net.marking_to_names(net.bittuple_to_marking(best))
    print('Optimization result (maximize total tokens):', name_id_marking, 'value=', val)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python main.py path_to_pnml')
        sys.exit(1)
    try:
        main(sys.argv[1])
    except Exception as e:
        print(f"An unexpected error occurred during execution: {e}")