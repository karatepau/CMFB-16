import argparse
import re
import os
import sys

# ==========================================
# CMFB-16 ARCHITECTURE CONFIGURATION
# ==========================================
# Exact pin mapping for the 64-bit instruction
BIT_IMM     = 0   # Bits 15-0 (ImmediateData)
BIT_REG_D   = 16  # Bits 19-16 (WAddr / Destination)
BIT_REG_A   = 20  # Bits 23-20 (RAddrA)
BIT_REG_B   = 24  # Bits 27-24 (RAddrB)
# Bits 35-28 are unused (kept at 0)
BIT_JE      = 36  # Bit 36 (Jump Enable)
BIT_ALU_OP  = 37  # Bits 40-37 (AluOp)
BIT_WE      = 41  # Bit 41 (Write Enable)
BIT_ALU_SRC = 42  # Bit 42 (ALUSrc)
BIT_RES_SRC = 43  # Bit 43 (ResultSrc)
# Bits 63-44 are unused (00000...)

ALU_OPS = {
    'ADD': 0b0000, 'ADDI': 0b0000, 'LI': 0b0000,
    'ADDC': 0b0001, 'SUB': 0b0010, 'SUBC': 0b0011,
    'AND': 0b0100, 'OR': 0b0101, 'XOR': 0b0110,
    'NOT': 0b0111, 'SHL': 0b1000, 'SHR': 0b1001,
    'MUL': 0b1010, 'POPC': 0b1011, 'MOV': 0b1111, 'PASS': 0b1111,
    'JMP': 0b0000  # ALU operation doesn't matter for JMP
}

def parse_reg(reg_str):
    """Converts 'R5' to the integer 5"""
    return int(reg_str.upper().replace('R', '').strip())

def assemble(input_file, output_file):
    with open(input_file, 'r') as f:
        lines = f.readlines()

    # --- PASS 1: Clean code and resolve labels ---
    cleaned_lines = []
    labels = {}
    address = 0

    for raw_line in lines:
        line = raw_line.split('#')[0].strip() # Remove comments
        if not line: continue
        
        # Check if it is a label (ends with ':')
        if line.endswith(':'):
            label_name = line[:-1].strip()
            labels[label_name] = address
        else:
            cleaned_lines.append(line)
            address += 1 # Each instruction takes 1 word in ROM

    # --- PASS 2: Assemble instructions ---
    hex_output = ["v2.0 raw"] # Standard header for Digital/Logisim
    
    for idx, line in enumerate(cleaned_lines):
        # Replace commas with spaces to facilitate splitting
        parts = re.sub(r',', ' ', line).split()
        op = parts[0].upper()
        
        reg_d, reg_a, reg_b, imm = 0, 0, 0, 0
        alu_src, res_src, we, je = 0, 0, 1, 0 # WE=1 by default
        alu_op = ALU_OPS.get(op, 0)

        try:
            if op == 'JMP':
                we = 0  # Do not write to registers
                je = 1  # Activate bit 36
                target = parts[1]
                imm = labels[target] if target in labels else int(target)
                
            elif op == 'LI':
                reg_d = parse_reg(parts[1])
                imm = int(parts[2])
                res_src = 1 # Bypass ALU (ResultSrc = 1)
                
            elif op == 'MOV':
                reg_d = parse_reg(parts[1])
                reg_a = parse_reg(parts[2])
                
            elif op in ['ADDI']:
                reg_d = parse_reg(parts[1])
                reg_a = parse_reg(parts[2])
                imm = int(parts[3])
                alu_src = 1
                
            elif op in ['NOT', 'POPC']:
                reg_d = parse_reg(parts[1])
                reg_a = parse_reg(parts[2])
                
            else: # R-Type (ADD, SUB, MUL, etc.)
                reg_d = parse_reg(parts[1])
                reg_a = parse_reg(parts[2])
                reg_b = parse_reg(parts[3])
                
        except Exception as e:
            print(f"Syntax error on line '{line}': {e}")
            sys.exit(1)

        # Build the 64-bit word by shifting each part into place
        instruction = 0
        instruction |= (imm & 0xFFFF) << BIT_IMM
        instruction |= (reg_d & 0xF) << BIT_REG_D
        instruction |= (reg_a & 0xF) << BIT_REG_A
        instruction |= (reg_b & 0xF) << BIT_REG_B
        instruction |= (je & 0x1) << BIT_JE
        instruction |= (alu_op & 0xF) << BIT_ALU_OP
        instruction |= (we & 0x1) << BIT_WE
        instruction |= (alu_src & 0x1) << BIT_ALU_SRC
        instruction |= (res_src & 0x1) << BIT_RES_SRC

        # Convert to hexadecimal (zero-padded, 64 bits = 16 hex characters)
        hex_output.append(f"{instruction:016x}")

    # Save file
    with open(output_file, 'w') as f:
        f.write("\n".join(hex_output))
    print(f"Successfully assembled: {input_file} -> {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Assembler for the CMFB-16 CPU")
    parser.add_argument("input", help=".asm file to assemble")
    parser.add_argument("-o", "--output", help="Output file (optional)", default=None)
    
    args = parser.parse_args()
    
    if args.output is None:
        base_name = os.path.splitext(args.input)[0]
        out_file = f"{base_name}.hex"
    else:
        out_file = args.output
        
    assemble(args.input, out_file)
