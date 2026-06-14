import re
import os
import sys

# ==========================================
# CMFB-16 ARCHITECTURE CONFIGURATION (V6.0)
# ==========================================
BIT_IMM      = 0
BIT_REG_D    = 16
BIT_REG_A    = 20
BIT_REG_B    = 24

BIT_MEM_WE   = 29
BIT_MEM_READ = 30
BIT_ADDR_SRC = 31

BIT_PRT      = 32
BIT_JLZ      = 33
BIT_JZ       = 34
BIT_JGZ      = 35
BIT_JE       = 36
BIT_ALU_OP   = 37
BIT_WE       = 41
BIT_ALU_SRC  = 42
BIT_RES_SRC  = 43

ALU_OPS = {
    'ADD': 0b0000, 'SUB': 0b0010, 'AND': 0b0100, 'OR':  0b0101,
    'XOR': 0b0110, 'NOT': 0b0111, 'SHL': 0b1000, 'SHR': 0b1001,
    'MUL': 0b1010, 'MOV': 0b1111, 'PASS': 0b1111, 'CMP': 0b0010
}

# Direcciones memoria mapeada GPU
GPU_X0    = 0xFFF8
GPU_Y0    = 0xFFF9
GPU_X1    = 0xFFFA
GPU_Y1    = 0xFFFB
GPU_COLOR = 0xFFFC
GPU_CMD   = 0xFFFD

DEBUG = False

def log(msg):
    if DEBUG:
        print(f"  [DBG] {msg}")

# ==========================================
# PARSING
# ==========================================

def parse_reg(reg_str):
    s = reg_str.upper().strip()
    if not (s.startswith('R') and s[1:].isdigit()):
        raise ValueError(f"Registro invalido: '{reg_str}'")
    n = int(s[1:])
    if not (0 <= n <= 15):
        raise ValueError(f"Registro fuera de rango: R{n} (R0-R15)")
    return n

def parse_val(s, labels):
    s = s.upper().strip()
    if s.startswith('R') and s[1:].isdigit():
        return True, int(s[1:])
    if s in labels:
        return False, labels[s]
    try:
        return False, int(s, 0)
    except ValueError:
        raise ValueError(f"Valor invalido: '{s}'")

# ==========================================
# EMPAQUETADO
# ==========================================

def pack_instruction(imm=0, reg_d=0, reg_a=0, reg_b=0, mem_we=0, mem_read=0,
                     addr_src=0, prt=0, jlz=0, jz=0, jgz=0, je=0,
                     alu_op=0, we=1, alu_src=0, res_src=0):
    ins = 0
    ins |= (imm     & 0xFFFF) << BIT_IMM
    ins |= (reg_d   & 0xF)    << BIT_REG_D
    ins |= (reg_a   & 0xF)    << BIT_REG_A
    ins |= (reg_b   & 0xF)    << BIT_REG_B
    ins |= (mem_we  & 0x1)    << BIT_MEM_WE
    ins |= (mem_read& 0x1)    << BIT_MEM_READ
    ins |= (addr_src& 0x1)    << BIT_ADDR_SRC
    ins |= (prt     & 0x1)    << BIT_PRT
    ins |= (jlz     & 0x1)    << BIT_JLZ
    ins |= (jz      & 0x1)    << BIT_JZ
    ins |= (jgz     & 0x1)    << BIT_JGZ
    ins |= (je      & 0x1)    << BIT_JE
    ins |= (alu_op  & 0xF)    << BIT_ALU_OP
    ins |= (we      & 0x1)    << BIT_WE
    ins |= (alu_src & 0x1)    << BIT_ALU_SRC
    ins |= (res_src & 0x1)    << BIT_RES_SRC
    return ins

# ==========================================
# PSEUDO-INSTRUCCIONES BASE
# R13 = temporal de direccion
# R14 = temporal de valor inmediato
# ==========================================

def pseudo_li(rd, imm):
    """LI Rd, imm  — 1 instruccion."""
    v = imm & 0xFFFF
    log(f"LI R{rd}, 0x{v:04X}")
    return [pack_instruction(reg_d=rd, imm=v, res_src=1, we=1)]

def pseudo_st_reg(addr, rb):
    """
    Store registro Rb a direccion inmediata addr.
    LI R13, addr  /  ST [R13], Rb  — 2 instrucciones.
    """
    log(f"  -> LI R13, 0x{addr:04X}  ;  ST [R13], R{rb}")
    return [
        *pseudo_li(13, addr),
        pack_instruction(reg_a=13, reg_b=rb, mem_we=1, addr_src=1, we=0),
    ]

def pseudo_st_imm(addr, val):
    """
    Store inmediato val a direccion inmediata addr.
    LI R13, addr  /  LI R14, val  /  ST [R13], R14  — 3 instrucciones.
    """
    log(f"  -> LI R13, 0x{addr:04X}  ;  LI R14, {val}  ;  ST [R13], R14")
    return [
        *pseudo_li(13, addr),
        *pseudo_li(14, val),
        pack_instruction(reg_a=13, reg_b=14, mem_we=1, addr_src=1, we=0),
    ]

# ==========================================
# GPU: con polling (espera a que 0xFFFD == 0)
# ==========================================

def gpu_poll(current_address):
    """
    Espera hasta que [GPU_CMD] == 0 (GPU libre).
    Usa R13 como temporal (ya reservado para direcciones).
    Tamaño fijo: 4 instrucciones.
      LI  R13, GPU_CMD
      LD  R13, [R13]
      CMP R13, 0
      JGZ <poll_start>   # si CMD > 0, GPU ocupada, volver a leer
    """
    poll_start = current_address
    log(f"GPU_POLL @ {poll_start:#06x}")
    return [
        *pseudo_li(13, GPU_CMD),
        pack_instruction(reg_d=13, reg_a=13, mem_read=1, addr_src=1, we=1),
        pack_instruction(reg_d=0, reg_a=13, imm=0, alu_op=ALU_OPS["CMP"], alu_src=1, we=0),
        pack_instruction(imm=poll_start, we=0, jgz=1, alu_src=1),
    ]

def expand_gpu_line(parts, addr):
    """
    GPULINE Rx0 Ry0 Rx1 Ry1 Rcolor
    Poll (4) + 5 coords (10) + CMD=1 (3) = 17 instrucciones
    """
    if len(parts) < 6:
        raise ValueError("GPULINE requiere 5 argumentos: Rx0 Ry0 Rx1 Ry1 Rcolor")
    rx0 = parse_reg(parts[1])
    ry0 = parse_reg(parts[2])
    rx1 = parse_reg(parts[3])
    ry1 = parse_reg(parts[4])
    rc  = parse_reg(parts[5])
    log(f"GPULINE R{rx0} R{ry0} R{rx1} R{ry1} R{rc}")
    instrs = []
    instrs += gpu_poll(addr)
    instrs += pseudo_st_reg(GPU_X0,    rx0)
    instrs += pseudo_st_reg(GPU_Y0,    ry0)
    instrs += pseudo_st_reg(GPU_X1,    rx1)
    instrs += pseudo_st_reg(GPU_Y1,    ry1)
    instrs += pseudo_st_reg(GPU_COLOR, rc)
    instrs += pseudo_st_imm(GPU_CMD, 1)
    assert len(instrs) == 17, f"GPULINE genero {len(instrs)} instrucciones, esperado 17"
    return instrs

def expand_gpu_clear(parts, addr):
    """
    GPUCLEAR Rcolor
    Poll (4) + color (2) + CMD=2 (3) = 9 instrucciones
    """
    if len(parts) < 2:
        raise ValueError("GPUCLEAR requiere 1 argumento: Rcolor")
    rc = parse_reg(parts[1])
    log(f"GPUCLEAR R{rc}")
    instrs = []
    instrs += gpu_poll(addr)
    instrs += pseudo_st_reg(GPU_COLOR, rc)
    instrs += pseudo_st_imm(GPU_CMD, 2)
    assert len(instrs) == 9, f"GPUCLEAR genero {len(instrs)} instrucciones, esperado 9"
    return instrs

# ==========================================
# STACK: SP = R15
# ==========================================

def expand_push(rb):
    """
    PUSH Rb
    ST [R15], Rb  /  SUB R15, R15, 1  — 2 instrucciones.
    """
    return [
        pack_instruction(reg_a=15, reg_b=rb, mem_we=1, addr_src=1, we=0),
        pack_instruction(reg_d=15, reg_a=15, imm=1, alu_op=ALU_OPS['SUB'], we=1, alu_src=1),
    ]

def expand_pop(rd):
    """
    POP Rd
    ADD R15, R15, 1  /  LD Rd, [R15]  — 2 instrucciones.
    """
    return [
        pack_instruction(reg_d=15, reg_a=15, imm=1, alu_op=ALU_OPS['ADD'], we=1, alu_src=1),
        pack_instruction(reg_d=rd,  reg_a=15, mem_read=1, addr_src=1, we=1),
    ]

def expand_ret():
    """
    RET
    ADD R15,R15,1  /  LD R13,[R15]  /  JMP R13  — 3 instrucciones.
    """
    return [
        pack_instruction(reg_d=15, reg_a=15, imm=1, alu_op=ALU_OPS['ADD'], we=1, alu_src=1),
        pack_instruction(reg_d=13, reg_a=15, mem_read=1, addr_src=1, we=1),
        pack_instruction(reg_b=13, we=0, je=1, alu_src=0),
    ]

def expand_call(label_addr, current_address):
    """
    CALL label
    LI R13, ret_addr  /  ST [R15], R13  /  SUB R15,R15,1  /  JMP label
    — 4 instrucciones. Tamano fijo, return_addr = current + 4.
    """
    return_addr = current_address + 4
    return [
        *pseudo_li(13, return_addr),
        pack_instruction(reg_a=15, reg_b=13, mem_we=1, addr_src=1, we=0),
        pack_instruction(reg_d=15, reg_a=15, imm=1, alu_op=ALU_OPS['SUB'], we=1, alu_src=1),
        pack_instruction(imm=label_addr, we=0, je=1, alu_src=1),
    ]

# ==========================================
# DIVISION: shift-and-subtract (unsigned)
# DIV Rd, Ra, Rb  ->  Rd = Ra / Rb
# Destruye Ra. Usa R13 como temporal.
# Tamano fijo: 1 + 16*5 = 81 instrucciones.
# ==========================================

def expand_div(rd, ra, rb):
    instrs = []
    instrs += pseudo_li(rd, 0)
    for i in range(15, -1, -1):
        instrs += [pack_instruction(reg_d=13, reg_a=rb, imm=i,
                                    alu_op=ALU_OPS['SHL'], we=1, alu_src=1)]
        instrs += [pack_instruction(reg_d=0,  reg_a=ra, reg_b=13,
                                    alu_op=ALU_OPS['SUB'], we=0)]
        instrs.append(('JLZ_SKIP', i))
        instrs += [pack_instruction(reg_d=ra, reg_a=ra, reg_b=13,
                                    alu_op=ALU_OPS['SUB'], we=1)]
        instrs += [pack_instruction(reg_d=rd, reg_a=rd, imm=(1 << i),
                                    alu_op=ALU_OPS['OR'], we=1, alu_src=1)]
        instrs.append(('LABEL_SKIP', i))
    return instrs

def resolve_div(raw, current_address):
    # Primera pasada: calcular posiciones de LABEL_SKIP
    positions = {}
    pos = current_address
    for item in raw:
        if isinstance(item, tuple):
            if item[0] == 'LABEL_SKIP':
                positions[item[1]] = pos
        else:
            pos += 1
    # Segunda pasada: reemplazar JLZ_SKIP con instrucciones reales
    instrs = []
    for item in raw:
        if isinstance(item, tuple):
            if item[0] == 'JLZ_SKIP':
                instrs.append(pack_instruction(
                    imm=positions[item[1]], we=0, jlz=1, alu_src=1))
        else:
            instrs.append(item)
    return instrs

# ==========================================
# TAMANOS (para la pasada de etiquetas)
# ==========================================

def instruction_size(line):
    parts = re.sub(r',', ' ', line).split()
    if not parts:
        return 0
    op = parts[0].upper()
    sizes = {
        'MUL':      2,
        'GPULINE':  17,
        'GPUCLEAR': 9,
        'PUSH':     2,
        'POP':      2,
        'RET':      3,
        'CALL':     4,
        'DIV':      81,
    }
    return sizes.get(op, 1)

# ==========================================
# DECODE para --debug
# ==========================================

def decode_instruction(ins):
    imm      = (ins >> BIT_IMM)      & 0xFFFF
    reg_d    = (ins >> BIT_REG_D)    & 0xF
    reg_a    = (ins >> BIT_REG_A)    & 0xF
    reg_b    = (ins >> BIT_REG_B)    & 0xF
    mem_we   = (ins >> BIT_MEM_WE)   & 0x1
    mem_read = (ins >> BIT_MEM_READ) & 0x1
    addr_src = (ins >> BIT_ADDR_SRC) & 0x1
    jlz      = (ins >> BIT_JLZ)      & 0x1
    jz       = (ins >> BIT_JZ)       & 0x1
    jgz      = (ins >> BIT_JGZ)      & 0x1
    je       = (ins >> BIT_JE)       & 0x1
    alu_op   = (ins >> BIT_ALU_OP)   & 0xF
    we       = (ins >> BIT_WE)       & 0x1
    alu_src  = (ins >> BIT_ALU_SRC)  & 0x1
    res_src  = (ins >> BIT_RES_SRC)  & 0x1

    if res_src:
        return f"LI R{reg_d}, 0x{imm:04X}"
    if mem_we:
        addr = f"R{reg_a}" if addr_src else f"0x{imm:04X}"
        return f"ST [{addr}], R{reg_b}"
    if mem_read:
        addr = f"R{reg_a}" if addr_src else f"0x{imm:04X}"
        return f"LD R{reg_d}, [{addr}]"
    if je or jz or jlz or jgz:
        jtype = ("JMP" if je else "") + ("JZ" if jz else "") + ("JLZ" if jlz else "") + ("JGZ" if jgz else "")
        tgt = f"R{reg_b}" if not alu_src else f"0x{imm:04X}"
        return f"{jtype} {tgt}"
    op_names = {0:'ADD',2:'SUB',4:'AND',5:'OR',6:'XOR',7:'NOT',8:'SHL',9:'SHR',10:'MUL',15:'MOV'}
    opn = op_names.get(alu_op, f'ALU{alu_op}')
    src2 = f"0x{imm:04X}" if alu_src else f"R{reg_b}"
    we_s = "" if we else " [no-WE]"
    return f"R{reg_d} = R{reg_a} {opn} {src2}{we_s}"

# ==========================================
# ASSEMBLER PRINCIPAL
# ==========================================

def assemble(input_file, output_file, debug=False):
    global DEBUG
    DEBUG = debug

    if not os.path.exists(input_file):
        print(f"Error: '{input_file}' no encontrado")
        sys.exit(1)

    with open(input_file, 'r') as f:
        raw_lines = f.readlines()

    cleaned_lines = []
    labels = {}
    address = 0

    # ---- FASE 1: recopilar etiquetas ----
    for raw_line in raw_lines:
        line = raw_line.split('#')[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            lname = line[:-1].strip().upper()
            if lname in labels:
                print(f"[AVISO] Etiqueta duplicada: '{lname}'")
            labels[lname] = address
            log(f"Label '{lname}' -> {address}")
        else:
            cleaned_lines.append(line)
            size = instruction_size(line)
            address += size

    # ---- FASE 2: generacion de instrucciones ----
    hex_output = ["v2.0 raw"]
    current_address = 0
    errors = 0

    for line in cleaned_lines:
        parts = re.sub(r',', ' ', line).split()
        op = parts[0].upper()

        if debug:
            print(f"\n[{current_address:04X}] {line}")

        try:
            instrs = []

            # --- Saltos ---
            if op in ('JMP', 'JZ', 'JLZ', 'JGZ'):
                is_reg, val = parse_val(parts[1], labels)
                instrs = [pack_instruction(
                    reg_b  = val if is_reg else 0,
                    imm    = 0   if is_reg else val,
                    we     = 0,
                    je     = (op == 'JMP'),
                    jz     = (op == 'JZ'),
                    jlz    = (op == 'JLZ'),
                    jgz    = (op == 'JGZ'),
                    alu_src= 0 if is_reg else 1,
                )]

            # --- Carga inmediata ---
            elif op == 'LI':
                rd = parse_reg(parts[1])
                _, imm = parse_val(parts[2], labels)
                instrs = pseudo_li(rd, imm)

            # --- Memoria ---
            elif op == 'ST':
                ra = parse_reg(parts[1])
                rb = parse_reg(parts[2])
                instrs = [pack_instruction(reg_a=ra, reg_b=rb,
                                           mem_we=1, addr_src=1, we=0)]

            elif op == 'LD':
                rd = parse_reg(parts[1])
                ra = parse_reg(parts[2])
                instrs = [pack_instruction(reg_d=rd, reg_a=ra,
                                           mem_read=1, addr_src=1, we=1)]

            # --- Multiplicacion ---
            elif op == 'MUL':
                rd_l = parse_reg(parts[1])
                rd_h = parse_reg(parts[2])
                ra   = parse_reg(parts[3])
                rb   = parse_reg(parts[4])
                instrs = [
                    pack_instruction(reg_d=rd_l, reg_a=ra, reg_b=rb,
                                     alu_op=ALU_OPS['MUL'], prt=0),
                    pack_instruction(reg_d=rd_h, reg_a=ra, reg_b=rb,
                                     alu_op=ALU_OPS['MUL'], prt=1),
                ]

            # --- Division ---
            elif op == 'DIV':
                rd = parse_reg(parts[1])
                ra = parse_reg(parts[2])
                rb = parse_reg(parts[3])
                instrs = resolve_div(expand_div(rd, ra, rb), current_address)

            # --- Stack ---
            elif op == 'PUSH':
                instrs = expand_push(parse_reg(parts[1]))

            elif op == 'POP':
                instrs = expand_pop(parse_reg(parts[1]))

            elif op == 'RET':
                instrs = expand_ret()

            elif op == 'CALL':
                _, label_addr = parse_val(parts[1], labels)
                instrs = expand_call(label_addr, current_address)

            # --- GPU ---
            elif op == 'GPULINE':
                instrs = expand_gpu_line(parts, current_address)

            elif op == 'GPUCLEAR':
                instrs = expand_gpu_clear(parts, current_address)

            # --- CMP: resta sin guardar resultado (no tiene Rd) ---
            elif op == 'CMP':
                ra = parse_reg(parts[1])
                is_reg, val = parse_val(parts[2], labels)
                instrs = [pack_instruction(
                    reg_d  = 0,
                    reg_a  = ra,
                    reg_b  = val if is_reg else 0,
                    imm    = 0   if is_reg else val,
                    alu_op = ALU_OPS['CMP'],
                    alu_src= 0 if is_reg else 1,
                    we     = 0,
                )]

            # --- ALU generica ---
            elif op in ALU_OPS:
                alu_op = ALU_OPS[op]
                rd = parse_reg(parts[1])
                ra = parse_reg(parts[2])
                if len(parts) > 3:
                    is_reg, val = parse_val(parts[3], labels)
                    instrs = [pack_instruction(
                        reg_d  = rd,
                        reg_a  = ra,
                        reg_b  = val if is_reg else 0,
                        imm    = 0   if is_reg else val,
                        alu_op = alu_op,
                        alu_src= 0 if is_reg else 1,
                    )]
                else:
                    instrs = [pack_instruction(reg_d=rd, reg_a=ra, alu_op=alu_op)]

            else:
                print(f"Error: instruccion desconocida '{op}'  linea: {line!r}")
                errors += 1
                instrs = [0]  # placeholder para no desalinear etiquetas

            # Verificacion de tamano
            expected = instruction_size(line)
            if len(instrs) != expected:
                print(f"[ERROR INTERNO] '{op}' genero {len(instrs)} instrucciones, "
                      f"instruction_size dice {expected}.  linea: {line!r}")
                errors += 1

            for ins in instrs:
                if debug:
                    print(f"  {current_address:04X}: {ins:016x}  {decode_instruction(ins)}")
                hex_output.append(f"{ins:016x}")
                current_address += 1

        except Exception as e:
            import traceback
            print(f"Error en linea {line!r}:")
            traceback.print_exc()
            errors += 1

    if errors:
        print(f"\n{errors} error(es) encontrados. Abortando.")
        sys.exit(1)

    with open(output_file, 'w') as f:
        f.write("\n".join(hex_output))
    print(f"OK: {output_file}  ({current_address} instrucciones, "
          f"{len(labels)} etiquetas)")

# ==========================================
# ENTRY POINT
# ==========================================

if __name__ == "__main__":
    args = sys.argv[1:]
    debug = '--debug' in args
    args = [a for a in args if a != '--debug']

    if not args:
        print("Uso: python assembler.py input.asm [output.hex] [--debug]")
        sys.exit(0)

    input_file  = args[0]
    output_file = args[1] if len(args) > 1 else "out.hex"
    assemble(input_file, output_file, debug=debug)
