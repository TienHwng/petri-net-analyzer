from dd.autoref import BDD

# 1. Khởi tạo
bdd = BDD()
# Khai báo 9 biến x1 đến x9
vars = [f'x{i}' for i in range(1, 10)]
bdd.declare(*vars)

# 2. Định nghĩa 4 trạng thái (Markings) dưới dạng logic
# M0: 111 000 111
m0_expr = 'x1 & x2 & x3 & ~x4 & ~x5 & ~x6 & x7 & x8 & x9'

# M1: 011 100 010 (Phil 1 ăn -> Mất x1, x7, x9. Có x4)
m1_expr = '~x1 & x2 & x3 & x4 & ~x5 & ~x6 & ~x7 & x8 & ~x9'

# M2: 101 010 001 (Phil 2 ăn -> Mất x2, x7, x8. Có x5)
m2_expr = 'x1 & ~x2 & x3 & ~x4 & x5 & ~x6 & ~x7 & ~x8 & x9'

# M3: 110 001 100 (Phil 3 ăn -> Mất x3, x8, x9. Có x6)
m3_expr = 'x1 & x2 & ~x3 & ~x4 & ~x5 & x6 & x7 & ~x8 & ~x9'

# 3. Tạo BDD tổng hợp (Reachable Set)
# S = M0 OR M1 OR M2 OR M3
u = bdd.add_expr(f'({m0_expr}) | ({m1_expr}) | ({m2_expr}) | ({m3_expr})')

# 4. Xuất ra ảnh
print("drawing BDD...")
bdd.dump('dining_bdd.png', roots=[u])
print("Finished! Open file dining_bdd.png")