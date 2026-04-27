import argparse
import re
import os
import sys

# ==========================================
# CMFB-16 ARCHITECTURE CONFIGURATION
# ==========================================
# Posiciones de los bits en la instrucción de 64 bits
BIT_IMM      = 0   # Bits 15-0 (ImmediateData)
BIT_REG_D    = 16  # Bits 19-16 (WAddr / Destination)
BIT_REG_A    = 20  # Bits 23-20 (RAddrA)
BIT_REG_B    = 24  # Bits 27-24 (RAddrB)

# BLOQUE RAM (32-28)
BIT_MEM_WE   = 28  # Bit 28: Write Enable para RAM (1=Escribir)
BIT_MEM_REG  = 29  # Bit 29: MemToReg (0=ALU, 1=RAM)
BIT_ADDR_SRC = 30  # Bit 30: AddrSource (0=Inmediato, 1=Registro)

BIT_JLZ      = 33  # Bit 33 (Jump if < 0)
BIT_JZ       = 34  # Bit 34 (Jump if == 0)
BIT_JGZ      = 35  # Bit 35 (Jump if > 0)
BIT_JE       = 36  # Bit 36 (Jump Enable / Unconditional)
BIT_ALU_OP   = 37  # Bits 40-37 (AluOp)
BIT_WE       = 41  # Bit 41 (Write Enable para Registros)
BIT_ALU_SRC  = 42  # Bit 42 (ALUSrc: 0=RegB, 1=Inmediato)
BIT_RES_SRC  = 43  # Bit 43 (ResultSrc: 1=Carga Directa Inmediato)

ALU_OPS = {
    'ADD': 0b0000, 'ADDC': 0b0001, 'SUB': 0b0010, 'SUBC': 0b0011,
    'AND': 0b0100, 'OR':  0b0101, 'XOR': 0b0110, 'NOT':  0b0111,
    'SHL': 0b1000, 'SHR': 0b1001, 'MUL': 0b1010, 'POPC': 0b1011,
    'MOV': 0b1111, 'PASS': 0b1111
}

def parse_reg(reg_str):
    """Convierte 'R5' o 'r5' en el entero 5"""
    return int(reg_str.upper().replace('R', '').strip())

def parse_val(s, labels):
    """
    Determina si un argumento es un registro (R1), 
    una etiqueta (START) o un número (100).
    Retorna (es_registro, valor)
    """
    s = s.upper().strip()
    if s.startswith('R') and s[1:].isdigit():
        return True, int(s[1:])
    if s in labels:
        return False, labels[s]
    try:
        # Soporta decimal y hexadecimal (0x)
        return False, int(s, 0)
    except ValueError:
        return False, 0

def assemble(input_file, output_file):
    if not os.path.exists(input_file):
        print(f"Error: File {input_file} not found.")
        sys.exit(1)

    with open(input_file, 'r') as f:
        lines = f.readlines()

    # --- FASE 1: Limpieza y Etiquetas ---
    cleaned_lines = []
    labels = {}
    address = 0
    for raw_line in lines:
        line = raw_line.split('#')[0].strip() # Quitar comentarios
        if not line: continue
        
        if line.endswith(':'): # Es una etiqueta
            label_name = line[:-1].strip().upper()
            labels[label_name] = address
        else:
            cleaned_lines.append(line)
            address += 1

    # --- FASE 2: Generación de código ---
    hex_output = ["v2.0 raw"]
    
    for line in cleaned_lines:
        parts = re.sub(r',', ' ', line).split()
        op = parts[0].upper()
        
        # Inicialización de señales de control por defecto
        reg_d, reg_a, reg_b, imm = 0, 0, 0, 0
        alu_op = 0
        alu_src, res_src, we = 0, 0, 1
        je, jz, jlz, jgz = 0, 0, 0, 0
        mem_we, mem_reg, addr_src = 0, 0, 0
        
        try:
            # 1. SALTOS
            if op in ['JMP', 'JZ', 'JLZ', 'JGZ']:
                we = 0
                _, val = parse_val(parts[1], labels)
                imm = val
                if   op == 'JMP': je  = 1
                elif op == 'JZ':  jz  = 1
                elif op == 'JLZ': jlz = 1
                elif op == 'JGZ': jgz = 1

            # 2. CARGA INMEDIATA (LI Rd, 100)
            elif op == 'LI':
                reg_d = parse_reg(parts[1])
                _, imm = parse_val(parts[2], labels)
                res_src = 1

            # 3. MEMORIA (ST R_data, [Direccion/Reg]) / (LD R_dest, [Direccion/Reg])
            elif op == 'ST':
                we = 0
                mem_we = 1
                reg_a = parse_reg(parts[1]) # El dato a guardar viene por RA
                is_reg, val = parse_val(parts[2], labels)
                if is_reg:
                    reg_b = val    # Dirección desde registro
                    addr_src = 1
                else:
                    imm = val      # Dirección desde inmediato
            
            elif op == 'LD':
                reg_d = parse_reg(parts[1])
                mem_reg = 1
                is_reg, val = parse_val(parts[2], labels)
                if is_reg:
                    reg_a = val    # Dirección desde registro
                    addr_src = 1
                else:
                    imm = val      # Dirección desde inmediato

            # 4. OPERACIONES ALU (ADD, SUB, AND, XOR, MOV, etc.)
            elif op in ALU_OPS:
                alu_op = ALU_OPS[op]
                reg_d = parse_reg(parts[1])
                reg_a = parse_reg(parts[2])
                
                # Si hay 3 argumentos: Rd, Ra, (Rb o Inmediato)
                if len(parts) > 3:
                    is_reg, val = parse_val(parts[3], labels)
                    if is_reg:
                        reg_b = val
                        alu_src = 0
                    else:
                        imm = val
                        alu_src = 1
                # Operaciones de un solo operando (Rd, Ra)
                elif op in ['NOT', 'POPC', 'MOV', 'PASS']:
                    alu_src = 0
            
            else:
                print(f"Unknown instruction: {op}")
                sys.exit(1)

        except Exception as e:
            print(f"Error parsing line '{line}': {e}")
            sys.exit(1)

        # --- EMPAQUETADO DE LA INSTRUCCIÓN (64 BITS) ---
        ins = 0
        ins |= (imm & 0xFFFF)     << BIT_IMM
        ins |= (reg_d & 0xF)      << BIT_REG_D
        ins |= (reg_a & 0xF)      << BIT_REG_A
        ins |= (reg_b & 0xF)      << BIT_REG_B
        ins |= (mem_we & 0x1)     << BIT_MEM_WE
        ins |= (mem_reg & 0x1)    << BIT_MEM_REG
        ins |= (addr_src & 0x1)   << BIT_ADDR_SRC
        ins |= (jlz & 0x1)        << BIT_JLZ
        ins |= (jz & 0x1)         << BIT_JZ
        ins |= (jgz & 0x1)        << BIT_JGZ
        ins |= (je & 0x1)         << BIT_JE
        ins |= (alu_op & 0xF)     << BIT_ALU_OP
        ins |= (we & 0x1)         << BIT_WE
        ins |= (alu_src & 0x1)    << BIT_ALU_SRC
        ins |= (res_src & 0x1)    << BIT_RES_SRC

        hex_output.append(f"{ins:016x}")

    # Guardar archivo
    with open(output_file, 'w') as f:
        f.write("\n".join(hex_output))
    print(f"Assembly successful. Output: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CMFB-16 Assembler v2.0")
    parser.add_argument("input", help="Input .asm file")
    parser.add_argument("-o", "--output", help="Output .hex file")
    args = parser.parse_args()

    out_file = args.output if args.output else os.path.splitext(args.input)[0] + ".hex"
    assemble(args.input, out_file)
