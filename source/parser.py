import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple


class Color:
    GREEN = "\033[92m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"


class Place:
    def __init__(self, id: str, name: str = None, initial_marking: int = 0):
        self.id = id
        self.name = name if name else id
        self.initial_marking = initial_marking

    def __repr__(self):
        return (
            f"Place(id='{self.id}', name='{self.name}', tokens={self.initial_marking})"
        )


class Transition:
    def __init__(self, id: str, name: str = None):
        self.id = id
        self.name = name if name else id

    def __repr__(self):
        return f"Transition(id='{self.id}', name='{self.name}')"


class PetriNet:
    def __init__(self):
        self.places: Dict[str, Place] = {}
        self.transitions: Dict[str, Transition] = {}
        self.input_arcs: Dict[str, List[Tuple[str, int]]] = {}
        self.output_arcs: Dict[str, List[Tuple[str, int]]] = {}

        # GLOBAL FLAG: Tracks if the net is perfect or has errors
        self.is_valid: bool = True

    def __repr__(self):
        return (
            f"PetriNet(places={len(self.places)}, transitions={len(self.transitions)})"
        )


def validate_petrinet(net: PetriNet) -> bool:
    """
    Checks for logical inconsistencies (Isolated nodes, Dead transitions).
    Updates net.is_valid to False if errors are found.
    """
    if not net:
        return False

    # Check Transitions connectivity
    for trans_id in net.transitions:
        # Dead transition (no input)
        if trans_id not in net.input_arcs or not net.input_arcs[trans_id]:
            print(
                f"{Color.RED}❌ Error: Transition '{net.transitions[trans_id].name}' has no input arcs (Dead transition){Color.RESET}"
            )
            net.is_valid = False

        # Sink transition (no output)
        if trans_id not in net.output_arcs or not net.output_arcs[trans_id]:
            print(
                f"{Color.RED}❌ Error: Transition '{net.transitions[trans_id].name}' has no output arcs (Sink transition){Color.RESET}"
            )
            net.is_valid = False

    # Check for Isolated Places
    connected_places = set()
    for arcs in net.input_arcs.values():
        for p_id, _ in arcs:
            connected_places.add(p_id)
    for arcs in net.output_arcs.values():
        for p_id, _ in arcs:
            connected_places.add(p_id)

    for p_id in net.places:
        if p_id not in connected_places:
            print(
                f"{Color.RED}❌ Error: Place '{net.places[p_id].name}' is isolated (no arcs connected){Color.RESET}"
            )
            net.is_valid = False

    return net.is_valid


def parse_pnml(file_path: str) -> PetriNet:
    """
    Parses PNML, constructs PetriNet.
    Returns None only if parsing crashes or critical logic fails at the end.
    Detailed errors are printed, and net.is_valid is updated.
    """
    print(f"{Color.CYAN}Parsing file: {file_path}{Color.RESET}")
    print(f"{Color.CYAN}Validating Petri Net consistency...{Color.RESET}")

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        net = PetriNet()  # net.is_valid starts as True

        ns = {"pnml": "http://www.pnml.org/version-2009/grammar/pnml"}

        # 1. Parse Places
        for place_elem in root.findall(".//pnml:place", ns):
            place_id = place_elem.get("id")
            if not place_id:
                continue

            name = place_id
            name_elem = place_elem.find("pnml:name", ns)
            if name_elem is not None:
                text_elem = name_elem.find("pnml:text", ns)
                value_elem = name_elem.find("pnml:value", ns)
                if text_elem is not None and text_elem.text:
                    name = text_elem.text
                elif value_elem is not None and value_elem.text:
                    name = value_elem.text

            initial_marking = 0
            marking_elem = place_elem.find("pnml:initialMarking", ns)
            if marking_elem is not None:
                text_elem = marking_elem.find("pnml:text", ns)
                value_elem = marking_elem.find("pnml:value", ns)
                if text_elem is not None and text_elem.text:
                    try:
                        initial_marking = int(text_elem.text)
                    except ValueError:
                        initial_marking = 0
                elif value_elem is not None and value_elem.text:
                    try:
                        initial_marking = int(value_elem.text)
                    except ValueError:
                        initial_marking = 0

            net.places[place_id] = Place(place_id, name, initial_marking)

        # 2. Parse Transitions
        for trans_elem in root.findall(".//pnml:transition", ns):
            trans_id = trans_elem.get("id")
            if not trans_id:
                continue

            name = trans_id
            name_elem = trans_elem.find("pnml:name", ns)
            if name_elem is not None:
                text_elem = name_elem.find("pnml:text", ns)
                value_elem = name_elem.find("pnml:value", ns)
                if text_elem is not None and text_elem.text:
                    name = text_elem.text
                elif value_elem is not None and value_elem.text:
                    name = value_elem.text

            net.transitions[trans_id] = Transition(trans_id, name)

        # 3. Parse Arcs
        for arc_elem in root.findall(".//pnml:arc", ns):
            # --- LOCAL FLAG: Reset for every single arc ---
            current_arc_valid = True

            arc_id = arc_elem.get("id")
            source_id = arc_elem.get("source")
            target_id = arc_elem.get("target")

            # Check 1: Missing Attributes
            if not all([arc_id, source_id, target_id]):
                print(
                    f"{Color.RED}❌ Error: Arc found with missing attributes.{Color.RESET}"
                )
                net.is_valid = False  # Mark net as broken
                current_arc_valid = False  # Don't process this arc

            # If basic attributes are missing, skip to next arc immediately
            if not current_arc_valid:
                continue

            weight = 1
            inscription_elem = arc_elem.find("pnml:inscription", ns)
            if inscription_elem is not None:
                text_elem = inscription_elem.find("pnml:text", ns)
                value_elem = inscription_elem.find("pnml:value", ns)
                if text_elem is not None and text_elem.text:
                    try:
                        weight = int(text_elem.text)
                    except ValueError:
                        weight = 1
                elif value_elem is not None and value_elem.text:
                    try:
                        weight = int(value_elem.text)
                    except ValueError:
                        weight = 1

            # --- SPECIFIC ERROR CHECKING ---
            s_is_place = source_id in net.places
            s_is_trans = source_id in net.transitions
            t_is_place = target_id in net.places
            t_is_trans = target_id in net.transitions

            # Check 2: Unknown Nodes
            if not (s_is_place or s_is_trans):
                print(
                    f"{Color.RED}❌ Error: Arc '{arc_id}' references unknown Source ID '{source_id}'.{Color.RESET}"
                )
                net.is_valid = False
                current_arc_valid = False

            if not (t_is_place or t_is_trans):
                print(
                    f"{Color.RED}❌ Error: Arc '{arc_id}' references unknown Target ID '{target_id}'.{Color.RESET}"
                )
                net.is_valid = False
                current_arc_valid = False

            # Check 3: Illegal Connections (Bipartite violation)
            if s_is_place and t_is_place:
                print(
                    f"{Color.RED}❌ Error: Invalid Arc '{arc_id}' connects Place -> Place.{Color.RESET}"
                )
                net.is_valid = False
                current_arc_valid = False

            if s_is_trans and t_is_trans:
                print(
                    f"{Color.RED}❌ Error: Invalid Arc '{arc_id}' connects Transition -> Transition.{Color.RESET}"
                )
                net.is_valid = False
                current_arc_valid = False

            # Only add to net if THIS SPECIFIC ARC is valid
            if current_arc_valid:
                if s_is_place and t_is_trans:
                    if target_id not in net.input_arcs:
                        net.input_arcs[target_id] = []
                    net.input_arcs[target_id].append((source_id, weight))
                elif s_is_trans and t_is_place:
                    if source_id not in net.output_arcs:
                        net.output_arcs[source_id] = []
                    net.output_arcs[source_id].append((target_id, weight))

        # 4. Final Validation (Logical check)

        # This will print logical errors and update net.is_valid to False if needed
        validate_petrinet(net)

        # 5. DECISION POINT
        # We always return the 'net' object so you can see what was parsed.
        # But if 'net.is_valid' is False, the main function will know not to proceed.
        if not net.is_valid:
            print(
                f"\n{Color.RED}⛔ Petri Net consistency check failed (see errors above).{Color.RESET}"
            )
            print(f"{Color.RED}The task will NOT proceed.{Color.RESET}")
            return None  # Stop everything by returning None to satisfy your requirement

        print(f"{Color.GREEN}✅ Petri Net consistency check successfully.{Color.RESET}")
        return net

    except ET.ParseError as e:
        print(f"Cannot parse XML: {e}")
        return None
    except Exception as e:
        print(f"Unknown Error: {e}")
        return None


def print_petrinet_info(net: PetriNet):
    if not net:
        print("PetriNet is None!")
        return

    print("=== PETRI NET ===")
    print("\n📌 PLACES:")
    for place in net.places.values():
        print(f"   {place.name} (tokens: {place.initial_marking})")

    print("\n🔄 TRANSITIONS:")
    for trans in net.transitions.values():
        print(f"   {trans.name}")

    print("\n🔗 INPUT ARCS:")
    for trans_id, arcs in net.input_arcs.items():
        trans_name = net.transitions[trans_id].name
        for place_id, weight in arcs:
            place_name = net.places[place_id].name
            print(f"   {place_name} --[{weight}]--> {trans_name}")

    print("\n🔗 OUTPUT ARCS:")
    for trans_id, arcs in net.output_arcs.items():
        trans_name = net.transitions[trans_id].name
        for place_id, weight in arcs:
            place_name = net.places[place_id].name
            print(f"   {trans_name} --[{weight}]--> {place_name}")


if __name__ == "__main__":
    pnml_file = "Standard PNMLs/diningPhilosophers.pnml"

    # parse_pnml now returns None if invalid
    petri_net = parse_pnml(pnml_file)

    # This block ensures we ONLY print/proceed if the net is valid
    if petri_net:
        print_petrinet_info(petri_net)
    else:
        # If None is returned, nothing happens (program stops effectively)
        pass
