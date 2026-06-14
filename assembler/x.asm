# Dibuja una X roja en pantalla

LI R0, 0xF800    # R0 = rojo

LI R1, 10        # x0
LI R2, 10        # y0
LI R3, 54        # x1
LI R4, 54        # y1
GPULINE R1 R2 R3 R4 R0

LI R1, 54        # x0
LI R2, 10        # y0
LI R3, 10        # x1
LI R4, 54        # y1
GPULINE R1 R2 R3 R4 R0

HALT:
    JMP HALT
