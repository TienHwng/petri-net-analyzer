import xml.etree.ElementTree as ET
from typing import Dict, List, Tuple


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
		self.input_arcs: Dict[
			str, List[Tuple[str, int]]
		] = {}  # transition_id -> [(place_id, weight)]
		self.output_arcs: Dict[
			str, List[Tuple[str, int]]
		] = {}  # transition_id -> [(place_id, weight)]

	def __repr__(self):
		return (
			f"PetriNet(places={len(self.places)}, transitions={len(self.transitions)})"
		)


def parse_pnml(file_path: str) -> PetriNet:
	"""
	Parse PNML file và trả về đối tượng PetriNet
	"""
	try:
		tree = ET.parse(file_path)
		root = tree.getroot()
		net = PetriNet()

		# PNML namespace - quan trọng!
		ns = {"pnml": "http://www.pnml.org/version-2009/grammar/pnml"}

		# Parse places
		for place_elem in root.findall(".//pnml:place", ns):
			place_id = place_elem.get("id")
			if not place_id:
				continue

			# Get name (hỗ trợ cả text và value)
			name = place_id  # default
			name_elem = place_elem.find("pnml:name", ns)
			if name_elem is not None:
				text_elem = name_elem.find("pnml:text", ns)
				value_elem = name_elem.find("pnml:value", ns)
				if text_elem is not None and text_elem.text:
					name = text_elem.text
				elif value_elem is not None and value_elem.text:
					name = value_elem.text

			# Get initial marking
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

		# Parse transitions
		for trans_elem in root.findall(".//pnml:transition", ns):
			trans_id = trans_elem.get("id")
			if not trans_id:
				continue

			# Get name
			name = trans_id  # default
			name_elem = trans_elem.find("pnml:name", ns)
			if name_elem is not None:
				text_elem = name_elem.find("pnml:text", ns)
				value_elem = name_elem.find("pnml:value", ns)
				if text_elem is not None and text_elem.text:
					name = text_elem.text
				elif value_elem is not None and value_elem.text:
					name = value_elem.text

			net.transitions[trans_id] = Transition(trans_id, name)

		# Parse arcs
		for arc_elem in root.findall(".//pnml:arc", ns):
			arc_id = arc_elem.get("id")
			source_id = arc_elem.get("source")
			target_id = arc_elem.get("target")

			if not all([arc_id, source_id, target_id]):
				continue

			# Get arc weight (mặc định = 1)
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

			# Xác định loại arc
			if source_id in net.places and target_id in net.transitions:
				# Input arc: place -> transition
				if target_id not in net.input_arcs:
					net.input_arcs[target_id] = []
				net.input_arcs[target_id].append((source_id, weight))

			elif source_id in net.transitions and target_id in net.places:
				# Output arc: transition -> place
				if source_id not in net.output_arcs:
					net.output_arcs[source_id] = []
				net.output_arcs[source_id].append((target_id, weight))
			else:
				print(f"Warning: Arc {arc_id} có source/target không hợp lệ")

		return net

	except ET.ParseError as e:
		print(f"Lỗi parse XML: {e}")
		return None
	except Exception as e:
		print(f"Lỗi không xác định: {e}")
		return None


def print_petrinet_info(net: PetriNet):
	"""Hiển thị đơn giản, chỉ tên (dễ đọc)"""
	if not net:
		print("PetriNet is None!")
		return

	print("=== PETRI NET (SIMPLIFIED) ===")

	print("\n📌 PLACES:")
	for place in net.places.values():
		print(f"   '{place.name}' (tokens: {place.initial_marking})")

	print("\n🔄 TRANSITIONS:")
	for trans in net.transitions.values():
		print(f"   '{trans.name}'")

	print("\n🔗 INPUT ARCS:")
	# Input arcs: Place -> Transition
	for trans_id, arcs in net.input_arcs.items():
		trans_name = net.transitions[trans_id].name
		for place_id, weight in arcs:
			place_name = net.places[place_id].name
			print(f"   '{place_name}' --[{weight}]--> '{trans_name}'")

	print("\n🔗 OUTPUT ARCS:")
	# Output arcs: Transition -> Place
	for trans_id, arcs in net.output_arcs.items():
		trans_name = net.transitions[trans_id].name
		for place_id, weight in arcs:
			place_name = net.places[place_id].name
			print(f"   '{trans_name}' --[{weight}]--> '{place_name}'")


def validate_petrinet(net: PetriNet) -> bool:
	"""Kiểm tra tính hợp lệ của Petri net"""
	if not net:
		return False

	# Kiểm tra mỗi transition có ít nhất 1 input và 1 output
	for trans_id in net.transitions:
		if trans_id not in net.input_arcs or not net.input_arcs[trans_id]:
			print(f"Warning: Transition {trans_id} không có input arcs")
		if trans_id not in net.output_arcs or not net.output_arcs[trans_id]:
			print(f"Warning: Transition {trans_id} không có output arcs")

	return True


# Test với file PNML
if __name__ == "__main__":
	# Thay đổi đường dẫn đến file PNML của bạn
	pnml_file = "F:/MM-251-Assignment/Standard PNMLs/diningPhilosophers.pnml"

	print(f"Parsing file: {pnml_file}")
	petri_net = parse_pnml(pnml_file)

	if petri_net:
		print_petrinet_info(petri_net)
		validate_petrinet(petri_net)
	else:
		print("Failed to parse PNML file")
