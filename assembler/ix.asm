# ============================================================
# letras.asm — CMFB-16
# Lee un carácter desde memoria mapeada (0xFFFE = teclado).
# Si es 'i' (ASCII 105) -> dibuja una I blanca en pantalla
# Si es 'x' (ASCII 120) -> dibuja una X roja en pantalla
#
# Registros reservados por el assembler: R13, R14, R15
# ============================================================

# ---------- Inicializacion ----------
LI R15, 0x7FFF         # R15 = stack pointer

LI R0, 0xFFFF          # R0 = color blanco
LI R1, 0xF800          # R1 = color rojo (RGB565)
LI R2, 0x0000          # R2 = cero (reset teclado)

LI R3, 0xFFFE          # R3 = addr teclado

LI R4, 69             # R4 = ASCII 'i'
LI R5, 78             # R5 = ASCII 'x'

# ---------- Bucle principal ----------
LOOP:
    WAIT:
        LD R6, R3          # R6 = caracter leido
        CMP R6, 0      # comparar con 0
        JZ WAIT            # si cero, seguir esperando

    ST R3, R2              # resetear registro teclado

    CMP R6, R4         # R7 = char - 'i'
    JZ DRAW_I

    CMP R6, R5         # R7 = char - 'x'
    JZ DRAW_X

    JMP LOOP

# ============================================================
# Dibujar I blanca
# ============================================================
DRAW_I:
    LI R8, 10
    LI R9, 10
    LI R10, 54
    LI R11, 10
    GPULINE R8 R9 R10 R11 R0

    LI R8, 32
    LI R9, 10
    LI R10, 32
    LI R11, 54
    GPULINE R8 R9 R10 R11 R0

    LI R8, 10
    LI R9, 54
    LI R10, 54
    LI R11, 54
    GPULINE R8 R9 R10 R11 R0

    JMP LOOP

# ============================================================
# Dibujar X roja
# ============================================================
DRAW_X:
    LI R8, 10
    LI R9, 10
    LI R10, 54
    LI R11, 54
    GPULINE R8 R9 R10 R11 R1

    LI R8, 54
    LI R9, 10
    LI R10, 10
    LI R11, 54
    GPULINE R8 R9 R10 R11 R1

    JMP LOOP
