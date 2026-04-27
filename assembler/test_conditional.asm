# test_conditional.asm
LI R1, 10
LI R2, 10
SUB R3, R1, R2      # R3 = 10 - 10 = 0. ALU Flags should update.

JZ success          # If the zero flag is active, jump to 'success'

# Failure path
LI R15, 57005       # 0xDEAD in decimal
JMP end

success:
# Success path
LI R15, 48879       # 0xBEEF in decimal

end:
# Program ends here. Check R15 for 0xBEEF.
