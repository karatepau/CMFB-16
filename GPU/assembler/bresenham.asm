# =============================================
# CMFB-16 GPU V7.0 - DISPATCHER
# R15=1 → Bresenham
# R15=2 → Fill screen con R14
# Al acabar → R15=0
# =============================================

# --- Leer R15 y despachar ---
LI R9, 1
CMP R15, R9
JZ DO_BRESENHAM
LI R9, 2
CMP R15, R9
JZ DO_FILL
JMP DONE

# =============================================
# FILL: pintar toda la VRAM con R14
# =============================================
DO_FILL:
LI R3, 0x0000       # dirección actual = 0
LI R8, 0x0FFF       # dirección final

FILL_LOOP:
ST R3, R14          # WE activo → pinta píxel
CMP R3, R8
JZ DONE
ADD R3, R3, 1
JMP FILL_LOOP

# =============================================
# BRESENHAM GENERICO (todos los octantes)
#
# Registros:
#   R0  = |dx|
#   R1  = |dy|
#   R2  = error acumulado (p)
#   R3  = addr temporal (para ST)
#   R4  = cur_x
#   R5  = cur_y
#   R6  = signo_x  (+1 o 0xFFFF)
#   R7  = signo_y  (+1 o 0xFFFF)
#   R8  = contador (= eje dominante)
#   R9  = scratch
# =============================================
DO_BRESENHAM:

# --- cur_x = X0, cur_y = Y0 ---
ADD R4, R10, 0
ADD R5, R11, 0

# --- dx = X1 - X0, luego |dx| y signo_x ---
SUB R0, R12, R10
LI R9, 0
CMP R0, R9
JLZ DX_NEG
LI R6, 1
JMP DX_DONE
DX_NEG:
LI R6, 0xFFFF
LI R9, 0
SUB R0, R9, R0
DX_DONE:

# --- dy = Y1 - Y0, luego |dy| y signo_y ---
SUB R1, R13, R11
LI R9, 0
CMP R1, R9
JLZ DY_NEG
LI R7, 1
JMP DY_DONE
DY_NEG:
LI R7, 0xFFFF
LI R9, 0
SUB R1, R9, R1
DY_DONE:

# -----------------------------------------------
# Detectar eje dominante: si dy > dx → MODO_Y
# CMP compara R0-R1; si resultado < 0 → dx < dy
# -----------------------------------------------
CMP R0, R1
JLZ MODO_Y

# -----------------------------------------------
# MODO X: eje dominante = X (dx >= dy)
# Avanza X siempre, Y condicionalmente.
# p inicial = 2*dy - dx
# -----------------------------------------------
MODO_X:
ADD R2, R1, R1      # p = 2*dy
SUB R2, R2, R0      # p = 2*dy - dx
ADD R8, R0, 0       # contador = dx

DRAW_LOOP_X:
# Pintar píxel: addr = cur_y*64 + cur_x
ADD R3, R5, R5
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3      # R3 = cur_y * 64
ADD R3, R3, R4      # R3 = cur_y * 64 + cur_x
ST R3, R14          # WE activo → pinta píxel

# Si contador == 0, terminar
LI R9, 0
CMP R8, R9
JZ DONE

# Siempre avanza X
ADD R4, R4, R6

# Evaluar p
LI R9, 0
CMP R2, R9
JLZ PX_NEG

# p >= 0: avanza Y, p += 2*dy - 2*dx
ADD R5, R5, R7
ADD R9, R1, R1
ADD R2, R2, R9
ADD R9, R0, R0
SUB R2, R2, R9
JMP PX_DONE

PX_NEG:
# p < 0: p += 2*dy
ADD R9, R1, R1
ADD R2, R2, R9

PX_DONE:
SUB R8, R8, 1
JMP DRAW_LOOP_X

# -----------------------------------------------
# MODO Y: eje dominante = Y (dy > dx)
# Avanza Y siempre, X condicionalmente.
# p inicial = 2*dx - dy
# -----------------------------------------------
MODO_Y:
ADD R2, R0, R0      # p = 2*dx
SUB R2, R2, R1      # p = 2*dx - dy
ADD R8, R1, 0       # contador = dy

DRAW_LOOP_Y:
# Pintar píxel: addr = cur_y*64 + cur_x
ADD R3, R5, R5
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3
ADD R3, R3, R3      # R3 = cur_y * 64
ADD R3, R3, R4      # R3 = cur_y * 64 + cur_x
ST R3, R14          # WE activo → pinta píxel

# Si contador == 0, terminar
LI R9, 0
CMP R8, R9
JZ DONE

# Siempre avanza Y
ADD R5, R5, R7

# Evaluar p
LI R9, 0
CMP R2, R9
JLZ PY_NEG

# p >= 0: avanza X, p += 2*dx - 2*dy
ADD R4, R4, R6
ADD R9, R0, R0
ADD R2, R2, R9
ADD R9, R1, R1
SUB R2, R2, R9
JMP PY_DONE

PY_NEG:
# p < 0: p += 2*dx
ADD R9, R0, R0
ADD R2, R2, R9

PY_DONE:
SUB R8, R8, 1
JMP DRAW_LOOP_Y

# =============================================
# DONE: setear R15 = 0 y halt
# =============================================
DONE:
LI R15, 0
JMP DONE
