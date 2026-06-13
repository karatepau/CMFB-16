import re
import os
import sys

# ==========================================
# CMFB-16 ARCHITECTURE CONFIGURATION (V7.0)
# ==========================================
BIT_IMM      = 0   
BIT_REG_D    = 16  
BIT_REG_A    = 20  
BIT_REG_B    = 24  

BIT_MEM_WE   = 35  # WriteRAM
BIT_MEM_READ = 36  # ReadRAM
BIT_JLZ      = 37  
BIT_JZ       = 38  
BIT_JMP      = 39  
BIT_ALU_OP   = 40  # 0=ADD, 1=SUB (1 bit)
BIT_WE       = 41  # Write Enable del Banco de Registros
BIT_ALU_SRC  = 42  
BIT_RES_SRC  = 43  

# ADDR_SRC: usa REG_A como dirección de memoria (bit 31, igual que antes)
BIT_ADDR_SRC = 31

ALU_OPS = {
    'ADD': 0,
    'SUB': 1,
    'CMP': 1,  # CMP es un SUB sin write-back
    'MOV': 0,  # MOV usa ADD con imm=0
}

def parse_reg(reg_str):
    return int(reg_str.upper().replace('R', '').strip())

def parse_val(s, labels):
    s = s.upper().strip()
    if s.startswith('R') and s[1:].isdigit():
        return True, int(s[1:])
    if s in labels:
        return False, labels[s]
    try:
        return False, int(s, 0)
    except ValueError:
        return False, 0

def pack_instruction(imm=0, reg_d=0, reg_a=0, reg_b=0,
                     mem_we=0, mem_read=0, addr_src=0,
                     jlz=0, jz=0, jmp=0,
                     alu_op=0, we=1, alu_src=0, res_src=0):
    ins = 0
    ins |= (imm      & 0xFFFF) << BIT_IMM
    ins |= (reg_d    & 0xF)    << BIT_REG_D
    ins |= (reg_a    & 0xF)    << BIT_REG_A
    ins |= (reg_b    & 0xF)    << BIT_REG_B
    ins |= (addr_src & 0x1)    << BIT_ADDR_SRC
    ins |= (mem_we   & 0x1)    << BIT_MEM_WE
    ins |= (mem_read & 0x1)    << BIT_MEM_READ
    ins |= (jlz      & 0x1)    << BIT_JLZ
    ins |= (jz       & 0x1)    << BIT_JZ
    ins |= (jmp      & 0x1)    << BIT_JMP
    ins |= (alu_op   & 0x1)    << BIT_ALU_OP
    ins |= (we       & 0x1)    << BIT_WE
    ins |= (alu_src  & 0x1)    << BIT_ALU_SRC
    ins |= (res_src  & 0x1)    << BIT_RES_SRC
    return ins

def assemble(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: {input_file} no encontrado")
        sys.exit(1)
    with open(input_file, 'r') as f:
        lines = f.readlines()

    cleaned_lines = []
    labels = {}
    address = 0

    # FASE 1: Resolución de etiquetas
    for raw_line in lines:
        line = raw_line.split('#')[0].strip()
        if not line:
            continue
        if line.endswith(':'):
            labels[line[:-1].strip().upper()] = address
        else:
            cleaned_lines.append(line)
            address += 1

    # FASE 2: Generación de código
    hex_output = ["v2.0 raw"]
    for line in cleaned_lines:
        parts = re.sub(r',', ' ', line).split()
        op = parts[0].upper()

        try:
            # ── Saltos ──────────────────────────────────────────────
            if op == 'JMP':
                _, val = parse_val(parts[1], labels)
                hex_output.append(f"{pack_instruction(imm=val, we=0, jmp=1):016x}")

            elif op == 'JZ':
                _, val = parse_val(parts[1], labels)
                hex_output.append(f"{pack_instruction(imm=val, we=0, jz=1):016x}")

            elif op == 'JLZ':
                _, val = parse_val(parts[1], labels)
                hex_output.append(f"{pack_instruction(imm=val, we=0, jlz=1):016x}")

            # ── Carga inmediata ──────────────────────────────────────
            elif op == 'LI':
                rd = parse_reg(parts[1])
                _, imm = parse_val(parts[2], labels)
                hex_output.append(f"{pack_instruction(reg_d=rd, imm=imm, alu_src=1, res_src=1):016x}")
                # alu_src=1 → ALU usa imm; res_src=1 → RES viene de resultado LI (bypass)

            # ── Memoria ─────────────────────────────────────────────
            elif op == 'ST':
                # ST Ra, Rb  →  [Ra] = Rb
                ra, rb = parse_reg(parts[1]), parse_reg(parts[2])
                hex_output.append(f"{pack_instruction(reg_a=ra, reg_b=rb, mem_we=1, addr_src=1, we=0):016x}")

            elif op == 'LD':
                # LD Rd, Ra  →  Rd = [Ra]
                rd, ra = parse_reg(parts[1]), parse_reg(parts[2])
                hex_output.append(f"{pack_instruction(reg_d=rd, reg_a=ra, mem_read=1, addr_src=1, we=1):016x}")

            # ── ALU ─────────────────────────────────────────────────
            elif op == 'ADD':
                rd, ra = parse_reg(parts[1]), parse_reg(parts[2])
                is_reg, val = parse_val(parts[3], labels)
                hex_output.append(f"{pack_instruction(reg_d=rd, reg_a=ra,
                    reg_b=(val if is_reg else 0),
                    imm=(0 if is_reg else val),
                    alu_op=0, we=1,
                    alu_src=(0 if is_reg else 1)):016x}")

            elif op == 'CMP':
                # CMP Ra, Rb/imm  →  flags = Ra - Rb, sin Rd, sin write-back
                ra = parse_reg(parts[1])
                is_reg, val = parse_val(parts[2], labels)
                hex_output.append(f"{pack_instruction(reg_d=0, reg_a=ra, reg_b=(val if is_reg else 0), imm=(0 if is_reg else val), alu_op=1, we=0, alu_src=(0 if is_reg else 1)):016x}")

            elif op == 'SUB':
                rd, ra = parse_reg(parts[1]), parse_reg(parts[2])
                is_reg, val = parse_val(parts[3], labels)
                hex_output.append(f"{pack_instruction(reg_d=rd, reg_a=ra, reg_b=(val if is_reg else 0), imm=(0 if is_reg else val), alu_op=1, we=1, alu_src=(0 if is_reg else 1)):016x}")

            elif op == 'MOV':
                # MOV Rd, Ra  →  Rd = Ra + 0
                rd, ra = parse_reg(parts[1]), parse_reg(parts[2])
                hex_output.append(f"{pack_instruction(reg_d=rd, reg_a=ra, alu_op=0, we=1):016x}")

            else:
                print(f"Error: instrucción desconocida '{op}' en línea '{line}'")
                sys.exit(1)

        except Exception as e:
            print(f"Error en línea '{line}': {e}")
            sys.exit(1)

    with open(output_file, 'w') as f:
        f.write("\n".join(hex_output))
    print(f"Ensamblado con éxito: {output_file} ({len(hex_output)-1} instrucciones)")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python assembler.py input.asm [output.hex]")
    else:
        assemble(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "out.hex")
