import re

def mirror_4bits(n):
    """Reverses the bit order for the custom ALU (e.g., 1011 becomes 1101)."""
    res = 0
    for i in range(4):
        res <<= 1
        res |= (n & 1)
        n >>= 1
    return res

def assemble(input_file, output_file):
    # Updated ALU operation codes
    alu_codes = {
        "ADD":  0b0000, "ADDC": 0b0001, "SUB":  0b0010, "SUBC": 0b0011,
        "AND":  0b0100, "OR":   0b0101, "XOR":  0b0110, "NOT":  0b0111,
        "SHL":  0b1000, "SHR":  0b1001, "MUL":  0b1010, "POPC": 0b1011,
        "PASS": 0b1111, # Custom Pass A instruction
        "MOV":  0b1111, # MOV uses PASS A
        "LI":   0b0000, # Load Immediate uses ADD internally
        "ADDI": 0b0000  # Add Immediate uses ADD internally
    }

    hex_output = ["v2.0 raw"]

    with open(input_file, 'r') as f:
        for line in f:
            # Remove comments and strip whitespace
            line = line.split('#')[0].strip()
            if not line: continue

            # Extract parts, removing commas and extra spaces
            parts = [p for p in re.split(r'[,\s]+', line) if p]
            instr = parts[0].upper()
            
            d = 0; a = 0; b = 0; imm = 0

            # --- SMART PARSER ---
            if instr == "LI":
                # Syntax: LI R1, 10
                d = int(parts[1].replace('R', ''))
                imm = int(parts[-1]) # Last value is the immediate
            elif instr in ["MOV", "NOT", "PASS"]:
                # Syntax: MOV R1, R2 (Uses AInput only)
                d = int(parts[1].replace('R', ''))
                a = int(parts[2].replace('R', ''))
            elif instr == "ADDI":
                # Syntax: ADDI R1, R2, 20
                d = int(parts[1].replace('R', ''))
                a = int(parts[2].replace('R', ''))
                imm = int(parts[-1])
            else:
                # Standard syntax: ADD R1, R2, R3
                d = int(parts[1].replace('R', ''))
                a = int(parts[2].replace('R', ''))
                b = int(parts[3].replace('R', ''))
                if len(parts) > 4: imm = int(parts[4])

            # --- CONTROL LOGIC ---
            res_src = 1 if instr == "LI" else 0 
            alu_src = 1 if instr in ["LI", "ADDI"] else 0 # 1 to read the Immediate
            we = 1                              
            
            raw_op = alu_codes.get(instr, 0)
            alu_op = mirror_4bits(raw_op) 
            
            # Instruction Packing (44-bit Word)
            control = (res_src << 15) | (alu_src << 14) | (we << 13) | (alu_op << 9)
            word = (control << 28) | (b << 24) | (a << 20) | (d << 16) | (imm & 0xFFFF)
            
            hex_output.append(f"{word:011x}")

    with open(output_file, 'w') as f:
        f.write("\n".join(hex_output))
    print(f"Assembly successful: {output_file} generated.")

if __name__ == "__main__":
    assemble("program.asm", "program.hex")
