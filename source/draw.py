import xml.etree.ElementTree as ET
import graphviz
import os
import sys

class PetriNetVisualizer:
    def __init__(self, pnml_file):
        # 1. Parse XML File
        try:
            tree = ET.parse(pnml_file)
            root = tree.getroot()
        except Exception as e:
            print(f"Error parsing XML file: {e}")
            sys.exit(1)
        
        # Define PNML namespace based on your file content
        ns = {'pnml': 'http://www.pnml.org/version-2009/grammar/pnml'}
        
        self.places = []
        self.transitions = []
        self.arcs = []
        self.marking = {}

        # 2. Parse Places and Initial Markings
        for p in root.findall('.//pnml:place', ns):
            p_id = p.get('id')
            self.places.append(p_id)
            
            # Extract initial token count if it exists
            # Structure: <initialMarking><text>1</text></initialMarking>
            init_mark = p.find('pnml:initialMarking/pnml:text', ns)
            if init_mark is not None:
                self.marking[p_id] = int(init_mark.text)
            else:
                self.marking[p_id] = 0

        # 3. Parse Transitions
        for t in root.findall('.//pnml:transition', ns):
            t_id = t.get('id')
            self.transitions.append(t_id)

        # 4. Parse Arcs
        for a in root.findall('.//pnml:arc', ns):
            source = a.get('source')
            target = a.get('target')
            # Default weight is 1 (add logic here if your PNML has specific weights)
            self.arcs.append({'source': source, 'target': target, 'weight': 1})
            
        self.step_count = 0
        print(f"Successfully loaded Petri Net: {len(self.places)} Places, {len(self.transitions)} Transitions.")

    def get_enabled_transitions(self):
        """Finds all transitions that are ready to fire."""
        enabled = []
        for t in self.transitions:
            is_enabled = True
            # Find all arcs going INTO this transition
            input_arcs = [a for a in self.arcs if a['target'] == t]
            
            for arc in input_arcs:
                place_name = arc['source']
                weight = arc.get('weight', 1)
                # Condition: Place must have enough tokens
                if self.marking.get(place_name, 0) < weight:
                    is_enabled = False
                    break
            
            if is_enabled:
                enabled.append(t)
        return enabled

    def fire_transition(self, t_name):
        """Executes the firing logic: Consume input tokens, produce output tokens."""
        print(f"Executing Step {self.step_count + 1}: Firing '{t_name}'")
        
        # 1. Consume tokens from Input Places
        input_arcs = [a for a in self.arcs if a['target'] == t_name]
        for arc in input_arcs:
            self.marking[arc['source']] -= arc.get('weight', 1)

        # 2. Produce tokens at Output Places
        output_arcs = [a for a in self.arcs if a['source'] == t_name]
        for arc in output_arcs:
            self.marking[arc['target']] += arc.get('weight', 1)
            
        self.step_count += 1

    def draw(self, filename=None, highlight_trans=None):
        """Renders the current state to a PNG image."""
        if not filename:
            filename = f"dining_step_{self.step_count}"
            
        dot = graphviz.Digraph(comment='Dining Philosophers', format='png')
        dot.attr(rankdir='TB') # Top to Bottom layout

        # Draw Places
        for p in self.places:
            tokens = self.marking[p]
            label = f"{p}\n({tokens})"
            
            # Logic: If place has tokens, color it light blue
            if tokens > 0:
                dot.node(p, label=label, shape='circle', style='filled', fillcolor='lightblue')
            else:
                dot.node(p, label=label, shape='circle')

        # Draw Transitions
        enabled_list = self.get_enabled_transitions()
        for t in self.transitions:
            fillcolor = 'white'
            if t == highlight_trans:
                fillcolor = 'red'      # Currently firing
            elif t in enabled_list:
                fillcolor = '#90EE90'  # Enabled (Green)
            
            dot.node(t, label=t, shape='box', style='filled', fillcolor=fillcolor)

        # Draw Arcs
        for arc in self.arcs:
            dot.edge(arc['source'], arc['target'])

        try:
            output_path = dot.render(filename, cleanup=True)
            print(f"-> Image saved: {output_path}")
        except Exception as e:
            print(f"Visualization Error (Is Graphviz installed?): {e}")

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    # 1. Setup File Paths
    # Get the directory where this script resides (source folder)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Construct path to the PNML file in the sibling directory
    pnml_path = os.path.join(current_dir, '..', 'Standard PNMLs', 'diningPhilosophers.pnml')
    pnml_path = os.path.normpath(pnml_path)

    print(f"Looking for input file at: {pnml_path}")

    if not os.path.exists(pnml_path):
        print("Error: File not found!")
        print("Please ensure the folder structure is: 'Standard PNMLs/diningPhilosophers.pnml'")
        sys.exit(1)

    # 2. Initialize Visualizer
    pn = PetriNetVisualizer(pnml_path)
    
    # 3. Interactive Loop
    while True:
        # Check enabled transitions
        enabled_trans = pn.get_enabled_transitions()
        
        # Draw current state
        pn.draw()
        
        print("\n" + "="*40)
        print(f"Current Marking: {pn.marking}")
        
        if not enabled_trans:
            print("DEADLOCK! No enabled transitions available.")
            break
            
        print(f"Enabled Transitions: {enabled_trans}")
        
        # User Selection Logic
        if len(enabled_trans) == 1:
            choice = enabled_trans[0]
            input(f"Press Enter to fire '{choice}'...")
        else:
            choice = input(f"Enter transition to fire {enabled_trans} (or 'q' to quit): ")
            if choice.lower() == 'q':
                break
            if choice not in enabled_trans:
                print("Invalid selection! Please choose an enabled transition.")
                continue
        
        # Fire and repeat
        pn.fire_transition(choice)