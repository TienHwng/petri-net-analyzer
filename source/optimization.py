import time
from typing import Dict, Tuple, Any

def solve_optimization_explicit(markings_list: list, place_weights: Dict[str, int], net) -> Tuple[int, Dict[str, int], float]:
    """
    Finds the marking that maximizes c^T * M using the explicit list of markings.
    
    Args:
        markings_list: List of reachable markings (from BFS/DFS).
        place_weights: Dictionary mapping Place Names to integer weights.
        net: The PetriNet object (needed to map ID to Name).
        
    Returns:
        (max_score, best_marking, duration)
    """
    start_time = time.time()
    
    max_score = -float('inf')
    best_marking = None
    
    # Map Place IDs to Names once for faster lookup
    id_to_name = {p.id: p.name for p in net.places.values()}
    
    for m in markings_list:
        current_score = 0
        for p_id, token_count in m.items():
            if token_count > 0:
                p_name = id_to_name[p_id]
                weight = place_weights.get(p_name, 0)
                current_score += weight * token_count
        
        if current_score > max_score:
            max_score = current_score
            best_marking = m
            
    end_time = time.time()
    return max_score, best_marking, end_time - start_time


def solve_optimization_symbolic(bdd_manager, reached_node, var_to_name_map: Dict[str, str], place_weights: Dict[str, int]) -> Tuple[int, Dict[str, bool], float]:
    """
    Finds the marking that maximizes c^T * M by iterating over BDD solutions.
    
    Args:
        bdd_manager: The BDD manager instance.
        reached_node: The BDD node representing Reach(M0).
        var_to_name_map: Mapping from BDD variable (e.g., 'x_p1') to Place Name.
        place_weights: Dictionary mapping Place Names to integer weights.
        
    Returns:
        (max_score, best_solution_dict, duration)
    """
    start_time = time.time()
    
    max_score = -float('inf')
    best_solution = None
    
    # Iterate through all satisfying assignments (markings) in the BDD
    for sol in bdd_manager.pick_iter(reached_node):
        current_score = 0
        
        # sol is a dict like {'x_p1': True, 'x_p2': False, ...}
        for var, is_true in sol.items():
            # We only care about current state variables (x_) that are True (have tokens)
            if var.startswith("x_") and is_true:
                p_name = var_to_name_map.get(var)
                if p_name:
                    weight = place_weights.get(p_name, 0)
                    current_score += weight
        
        if current_score > max_score:
            max_score = current_score
            best_solution = sol
            
    end_time = time.time()
    return max_score, best_solution, end_time - start_time