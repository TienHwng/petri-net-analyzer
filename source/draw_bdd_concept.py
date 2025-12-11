import graphviz
import os

# Đường dẫn Graphviz (giữ nguyên như bạn đã setup)
graphviz_path = r'C:\Program Files\Graphviz\bin'
if os.path.exists(graphviz_path):
    os.environ["PATH"] += os.pathsep + graphviz_path

def draw_conceptual_bdd():
    dot = graphviz.Digraph(comment='Dining Philosophers BDD', format='png')
    
    # Thiết lập style: Vẽ từ trên xuống, đường nét thẳng
    dot.attr(rankdir='TB', splines='line')
    
    # --- 1. Tạo các NÚT (NODES) ---
    
    # Nút gốc
    dot.node('root', 'ROOT', shape='circle', style='filled', fillcolor='black', fontcolor='white', width='0.5')

    # Các nút quyết định (Decision Nodes) - Hình thoi
    dot.attr('node', shape='diamond', style='filled', fillcolor='#FFFACD') # Màu vàng nhạt
    dot.node('x4', 'Check x4\n(P1 Eating?)')
    dot.node('x5', 'Check x5\n(P2 Eating?)')
    dot.node('x6', 'Check x6\n(P3 Eating?)')

    # Các nút kiểm tra ràng buộc (Constraint Nodes) - Hình chữ nhật bo góc
    dot.attr('node', shape='Mrecord', style='filled', fillcolor='#E0FFFF') # Màu xanh nhạt
    dot.node('chk_m1', '{Check: x1, x7, x9|Must be 0}')
    dot.node('chk_m2', '{Check: x2, x7, x8|Must be 0}')
    dot.node('chk_m3', '{Check: x3, x8, x9|Must be 0}')

    # Các nút trạng thái kết quả (Terminal Nodes) - Hình chữ nhật đậm
    dot.attr('node', shape='box', style='filled', fillcolor='#90EE90') # Màu xanh lá
    dot.node('M0', 'State M0\n(Thinking)\n111 000 111')
    dot.node('M1', 'State M1\n(P1 Eats)\n011 100 010')
    dot.node('M2', 'State M2\n(P2 Eats)\n101 010 001')
    dot.node('M3', 'State M3\n(P3 Eats)\n110 001 100')

    # --- 2. Tạo các CUNG (EDGES) ---
    
    # Từ Root vào kiểm tra x4
    dot.edge('root', 'x4')

    # --- Nhánh x4 (P1 Eating) ---
    # Nếu x4 = 1 (P1 đang ăn) -> Sang kiểm tra ràng buộc -> Ra M1
    dot.edge('x4', 'chk_m1', label=' 1 (True) ', color='blue', fontcolor='blue')
    dot.edge('chk_m1', 'M1', style='bold')

    # Nếu x4 = 0 (P1 không ăn) -> Xuống kiểm tra x5
    dot.edge('x4', 'x5', label=' 0 (False) ', style='dashed')

    # --- Nhánh x5 (P2 Eating) ---
    # Nếu x5 = 1 -> Sang kiểm tra ràng buộc -> Ra M2
    dot.edge('x5', 'chk_m2', label=' 1 ', color='blue', fontcolor='blue')
    dot.edge('chk_m2', 'M2', style='bold')

    # Nếu x5 = 0 -> Xuống kiểm tra x6
    dot.edge('x5', 'x6', label=' 0 ', style='dashed')

    # --- Nhánh x6 (P3 Eating) ---
    # Nếu x6 = 1 -> Sang kiểm tra ràng buộc -> Ra M3
    dot.edge('x6', 'chk_m3', label=' 1 ', color='blue', fontcolor='blue')
    dot.edge('chk_m3', 'M3', style='bold')

    # Nếu x6 = 0 -> Nghĩa là không ai ăn cả -> Ra M0
    dot.edge('x6', 'M0', label=' 0 ', style='dashed')

    # --- 3. Lưu ảnh ---
    output_path = dot.render('bdd_concept_tree', cleanup=True)
    print(f"Finished drawing BDD Conceptual tree! File picture: {output_path}")

if __name__ == '__main__':
    draw_conceptual_bdd()