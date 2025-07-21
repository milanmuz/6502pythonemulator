import sys
import select
import pygame
import serial
from bios import BIOS 
from charrom import charROM 
from pygame.locals import *
import subprocess
subprocess.Popen(["python3", "vsp.py"])

VID_WIDTH = 40
VID_HEIGHT = 25

videomem = []
videomem = [0 for i in range(1000)]
colormem = []
colormem = [0 for i in range(1000)]
bgcolmem = []
bgcolmem = [0 for i in range(1000)]
xpos=0
ypos=0


RAM_SIZE = 0x8000
FLAG_CARRY = 0x01
FLAG_ZERO = 0x02
FLAG_INTERRUPT = 0x04
FLAG_DECIMAL = 0x08
FLAG_BREAK = 0x10
FLAG_CONSTANT = 0x20
FLAG_OVERFLOW = 0x40
FLAG_SIGN = 0x80
BASE_STACK = 0x100

pc = 0
sp = 0
a = 0
x = 0
y = 0
cpustatus = 0
instructions = 0
clockticks6502 = 0
clockgoal6502 = 0
oldpc = 0
ea = 0
reladdr = 0
value = 0
result = 0
opcode = 0
oldcpustatus = 0
useaccum = 0
# RAM = [0] * 0x8000
RAM = []
RAM = [0 for i in range(32768)]
RAM2 = []
RAM2 = [0 for i in range(4096)]
curkey = 0


def read6502(address):
    global curkey   
    if address == 0xF004:
        tmp,curkey=curkey,0
        return tmp 
    elif 0xC000 <= address:
        return BIOS[address - 0xC000]
    elif 0x8000+1000<=address<0x9000:
        return RAM2[address-(0x8000+1000)]
    elif 0x8000 <= address < 0x8000+1000:
        return videomem[address - 0x8000] 
    elif address < 0x8000:
        return RAM[address]     
    else:
        return 0

def write6502(address, value):
    address &= 0xFFFF
    value &= 0xFF
    if address < 0x8000:
        RAM[address] = value
    elif 0x8000 <= address < 0x8000+1000:
        if value >= 32 and value < 128:
            if value > 95:
                value -= 96 
        if value == 10:
            value = 32
        videomem[address-0x8000] = value
    elif 0x8000+1000<=address<0x9000:
        RAM2[address-(0x8000+1000)]=value
   



def saveaccum(n):
    global a
    a = n & 0x00FF

def setcarry():
    global cpustatus, FLAG_CARRY
    cpustatus |= FLAG_CARRY

def clearcarry():
    global cpustatus, FLAG_CARRY
    cpustatus &= ~FLAG_CARRY

def setzero():
    global cpustatus, FLAG_ZERO
    cpustatus |= FLAG_ZERO

def clearzero():
    global cpustatus, FLAG_ZERO
    cpustatus &= ~FLAG_ZERO

def setinterrupt():
    global cpustatus, FLAG_INTERRUPT
    cpustatus |= FLAG_INTERRUPT

def clearinterrupt():
    global cpustatus, FLAG_INTERRUPT
    cpustatus &= ~FLAG_INTERRUPT

def setdecimal():
    global cpustatus,FLAG_DECIMAL
    cpustatus |= FLAG_DECIMAL

def cleardecimal():
    global cpustatus, FLAG_DECIMAL
    cpustatus &= ~FLAG_DECIMAL

def setoverflow():
    global cpustatus, FLAG_OVERFLOW
    cpustatus |= FLAG_OVERFLOW

def clearoverflow():
    global cpustatus, FLAG_OVERFLOW
    cpustatus &= ~FLAG_OVERFLOW

def setsign():
    global cpustatus,FLAG_SIGN
    cpustatus |= FLAG_SIGN

def clearsign():
    global cpustatus, FLAG_SIGN
    cpustatus &= ~FLAG_SIGN

def zerocalc(n):
    if n & 0x00FF:
        clearzero()
    else:
        setzero()

def signcalc(n):
    if n & 0x0080:
        setsign()
    else:
        clearsign()

def carrycalc(n):
    if n & 0xFF00:
        setcarry()
    else:
        clearcarry()

def overflowcalc(n, m, o):
    if (n ^ m) & (n ^ o) & 0x0080:
        setoverflow()
    else:
        clearoverflow()

def push16(pushval):
    global sp, BASE_STACK
    pushval &= 0xFFFF
    write6502(BASE_STACK + sp, (pushval >> 8) & 0xFF)
    write6502(BASE_STACK + ((sp - 1) & 0xFF), pushval & 0xFF)
    sp -= 2

def push8(pushval):
    global sp, BASE_STACK
    pushval &= 0xFF
    write6502(BASE_STACK + sp, pushval)
    sp -= 1

def pull16():
    global sp, BASE_STACK
    
    temp16 = read6502(BASE_STACK + ((sp + 1) & 0xFF)) | (read6502(BASE_STACK + ((sp + 2) & 0xFF)) << 8)
    sp += 2
    return temp16 & 0xFFFF

def pull8():
    global sp, BASE_STACK
    
    sp += 1
    return read6502(BASE_STACK + sp) & 0xFF

def reset6502():
    global pc, a, x, y, sp, cpustatus, FLAG_CONSTANT
    
    pc = read6502(0xFFFC) | (read6502(0xFFFD) << 8)
    a = 0
    x = 0
    y = 0
    sp = 0xFD
    cpustatus |= FLAG_CONSTANT
    cpustatus &= 0xFF
    
def imp():
    pass

def acc():
    global useaccum
    useaccum = 0x0001

def imm():
    global ea, pc
    ea = pc
    pc += 1

def zp():
    global ea, pc
    ea = read6502(pc)
    ea &= 0xFFFF
    pc += 1

def zpx():
    global ea, pc, x
    ea = (read6502(pc) + x) & 0xFF
    pc += 1

def zpy():
    global ea, pc, y
    ea = (read6502(pc) + y) & 0xFF
    pc += 1

def rel():
    global reladdr, pc
    reladdr = read6502(pc)
    pc += 1
    if reladdr & 0x80:
        reladdr |= 0xFF00

def abso():
    global ea, pc
    ea = read6502(pc) | (read6502(pc + 1) << 8)
    ea &= 0xFFFF
    pc += 2

def absx():
    global ea, pc, x
    ea = read6502(pc) | (read6502(pc + 1) << 8)
    startpage = ea & 0xFF00
    ea += x
    ea &= 0xFFFF
    pc += 2

def absy():
    global ea, pc, y
    ea = read6502(pc) | (read6502(pc + 1) << 8)
    startpage = ea & 0xFF00
    ea += y
    ea &= 0xFFFF
    pc += 2


def ind():
    global ea, pc
    eahelp = read6502(pc) | (read6502(pc+1) << 8)
    eahelp2 = (eahelp & 0xFF00) | ((eahelp + 1) & 0x00FF)
    ea = read6502(eahelp) | (read6502(eahelp2) << 8)
    ea &= 0xFFFF
    pc += 2

def indx():
    global ea, pc, x
    eahelp = (read6502(pc) + x) & 0xFF
    ea = read6502(eahelp & 0x00FF) | (read6502((eahelp+1) & 0x00FF) << 8)
    ea &= 0xFFFF
    pc += 1

def indy():
    global ea, pc, y
    eahelp = read6502(pc)
    eahelp2 = (eahelp & 0xFF00) | ((eahelp + 1) & 0x00FF)
    ea = read6502(eahelp) | (read6502(eahelp2) << 8)
    startpage = ea & 0xFF00
    ea += y
    ea &= 0xFFFF
    pc += 1

def getvalue():
    global a, ea, useaccum
    if useaccum:
        return a & 0xFFFF
    else:
        return read6502(ea) & 0xFFFF

def getvalue16():
    global ea
    return (read6502(ea) | (read6502(ea+1) << 8)) & 0xFFFF

def putvalue(saveval):
    global ea, a, useaccum
    if useaccum:
        a = saveval & 0x00FF
    else:
        write6502(ea, saveval & 0x00FF)


def adc():
    global a, result, value, cpustatus, FLAG_CARRY
    value = getvalue()
    result = a + value + (cpustatus & FLAG_CARRY)
    result &= 0xFFFF
    carrycalc(result)
    zerocalc(result)
    overflowcalc(result, a, value)
    signcalc(result)
    
    saveaccum(result)
    

def op_and():
    global a,value, result 
    value = getvalue()
    result = a & value
    result &= 0xFFFF
    zerocalc(result)
    signcalc(result)
    
    saveaccum(result)
    

def asl():
    global value, result 
    value = getvalue()
    result = value << 1
    result &= 0xFFFF
    carrycalc(result)
    zerocalc(result)
    signcalc(result)
    
    putvalue(result)


def bcc():
    global pc, reladdr, clockticks6502, cpustatus, oldpc, FLAG_CARRY
    if (cpustatus & FLAG_CARRY) == 0:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def bcs():
    global pc, reladdr, clockticks6502, cpustatus, oldpc, FLAG_CARRY
    if (cpustatus & FLAG_CARRY) == FLAG_CARRY:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def beq():
    global pc, reladdr, clockticks6502, cpustatus,oldpc, FLAG_ZERO
    if (cpustatus & FLAG_ZERO) == FLAG_ZERO:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def op_bit():
    global cpustatus, value, a, result
    value = getvalue()
    result = a & value
    result &= 0xFFFF
    zerocalc(result)
    cpustatus = (cpustatus & 0x3F) | (value & 0xC0)
    cpustatus &= 0xFF


def bmi():
    global pc, cpustatus, clockticks6502,oldpc, FLAG_SIGN, reladdr
    if (cpustatus & FLAG_SIGN) == FLAG_SIGN:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def bne():
    global pc, clockticks6502,oldpc, cpustatus, FLAG_ZERO, reladdr
    if (cpustatus & FLAG_ZERO) == 0:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def bpl():
    global pc, clockticks6502,oldpc, cpustatus,FLAG_SIGN, reladdr
    if (cpustatus & FLAG_SIGN) == 0:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2  # check if jump crossed a page boundary
        else:
            clockticks6502 += 1

def brk():
    global pc, cpustatus, FLAG_BREAK
    pc += 1
    push16(pc)  # push next instruction address onto stack
    push8(cpustatus | FLAG_BREAK)  # push CPU cpustatus to stack
    setinterrupt()  # set interrupt flag
    pc = read6502(0xFFFE) | (read6502(0xFFFF) << 8)


def bvc():
    global pc, oldpc, reladdr, clockticks6502, cpustatus, FLAG_OVERFLOW
    
    if (cpustatus & FLAG_OVERFLOW) == 0:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2 #check if jump crossed a page boundary
        else:
            clockticks6502 += 1


def bvs():
    global pc, oldpc, reladdr, clockticks6502, cpustatus, FLAG_OVERFLOW
    
    if (cpustatus & FLAG_OVERFLOW) == FLAG_OVERFLOW:
        oldpc = pc
        pc += reladdr
        pc &= 0xFFFF
        if (oldpc & 0xFF00) != (pc & 0xFF00):
            clockticks6502 += 2 #check if jump crossed a page boundary
        else:
            clockticks6502 += 1


def clc():
    clearcarry()


def cld():
    cleardecimal()


def cli():
    clearinterrupt()


def clv():
    clearoverflow()

def cmp():
    global a,value, result 
    value = getvalue()
    result = a - value
    result &= 0xFFFF 
    if a >= (value & 0x00FF):
        setcarry()
    else:
        clearcarry()
        
    if a == (value & 0x00FF):
        setzero()
    else:
        clearzero()
      
    signcalc(result)

def cpx():
    global x, value, result 
    value = getvalue()
    result = x - value
    result &= 0xFFFF
    if x >= (value & 0x00FF):
        setcarry()
    else:
        clearcarry()
        
    if x == (value & 0x00FF):
        setzero()
    else:
        clearzero()
        
    signcalc(result)

def cpy():
    global y, value, result 
    value = getvalue()
    result = y - value
    result &= 0xFFFF
    if y >= (value & 0x00FF):
        setcarry()
    else:
        clearcarry()
        
    if y == (value & 0x00FF):
        setzero()
    else:
        clearzero()
        
    signcalc(result)


def dec():
    global value, result 
    value = getvalue()
    result = value - 1
    result &= 0xFFFF
    zerocalc(result)
    signcalc(result)
    putvalue(result)

def dex():
    global x
    x -= 1
    x &= 0xFF
    zerocalc(x)
    signcalc(x)

def dey():
    global y
    y -= 1
    y &= 0xFF
    zerocalc(y)
    signcalc(y)

def eor():
    global value, result, a
    value = getvalue()
    result = a ^ value
    result &= 0xFFFF
    zerocalc(result)
    signcalc(result)
    saveaccum(result)


def inc():
    global value, result
    value = getvalue()
    result = value + 1
    result &= 0xFFFF
    zerocalc(result)
    signcalc(result)

    putvalue(result)

def inx():
    global x
    x += 1
    x &= 0xFF
    zerocalc(x)
    signcalc(x)

def iny():
    global y
    y += 1
    y &= 0xFF
    zerocalc(y)
    signcalc(y)

def jmp():
    global pc, ea
    pc = ea

def jsr():
    global pc, ea
    push16(pc - 1)
    pc = ea

def lda():
    global value, a
    value = getvalue()
    a = (value & 0x00FF)
    a &= 0xFF
    zerocalc(a)
    signcalc(a)


def ldx():
    global value, x
    value = getvalue()
    x = (value & 0x00FF)
    x &= 0xFF
    zerocalc(x)
    signcalc(x)

def ldy():
    global value, y
    value = getvalue()
    y = (value & 0x00FF)
    y &= 0xFF
    zerocalc(y)
    signcalc(y)

def lsr():
    global value, result
    value = getvalue()
    result = value >> 1
    result &= 0xFFFF
    if (value & 1):
        setcarry()
    else:
        clearcarry()
    zerocalc(result)
    signcalc(result)
    putvalue(result)

def nop():
    pass

def ora():
    global value, result, a
    value = getvalue()
    result = (a | value)
    result &= 0xFFFF
    zerocalc(result)
    signcalc(result)
    saveaccum(result)



def pha():
    global a
    push8(a)

def php():
    global cpustatus, FLAG_BREAK
    push8(cpustatus | FLAG_BREAK)

def pla():
    global a
    a = pull8()

    zerocalc(a)
    signcalc(a)

def plp():
    global cpustatus, FLAG_CONSTANT
    cpustatus = pull8() | FLAG_CONSTANT

def rol():
    global value, result, FLAG_CARRY, cpustatus
    value = getvalue()
    result = (value << 1) | (cpustatus & FLAG_CARRY)
    result &= 0xFFFF
    carrycalc(result)
    zerocalc(result)
    signcalc(result)

    putvalue(result)

def ror():
    global value, result, FLAG_CARRY, cpustatus
    value = getvalue()
    result = (value >> 1) | ((cpustatus & FLAG_CARRY) << 7)
    result &= 0xFFFF
    if (value & 1):
        setcarry()
    else:
        clearcarry()
    zerocalc(result)
    signcalc(result)

    putvalue(result)


def rti():
    global cpustatus, pc, value
    cpustatus = pull8()
    value = pull16()
    pc = value

def rts():
    global pc, value
    value = pull16()
    pc = value + 1
    pc &= 0xFFFF

def sbc():
    global a, value, result, cpustatus, FLAG_CARRY
    value = getvalue() ^ 0x00FF
    result = a + value + (cpustatus & FLAG_CARRY)
    result &= 0xFFFF
    carrycalc(result)
    zerocalc(result)
    overflowcalc(result, a, value)
    signcalc(result)
    saveaccum(result)

def sec():
    setcarry()

def sed():
    setdecimal()

def sei():
    setinterrupt()

def sta():
    global a
    putvalue(a)

def stx():
    global x
    putvalue(x)

def sty():
    global y
    putvalue(y)


def tax():
    global x, a
    x = a
    zerocalc(x)
    signcalc(x)

def tay():
    global y, a
    y = a
    zerocalc(y)
    signcalc(y)

def tsx():
    global x, sp
    x = sp
    zerocalc(x)
    signcalc(x)

def txa():
    global a, x
    a = x
    zerocalc(a)
    signcalc(a)

def txs():
    global sp, x
    sp = x

def tya():
    global a, y
    a = y
    zerocalc(a)
    signcalc(a)


def nmi6502():
    global cpustatus, pc, FLAG_INTERRUPT
    push16(pc)
    push8(cpustatus)
    cpustatus |= FLAG_INTERRUPT
    cpustatus &= 0xFF
    pc = (read6502(0xFFFA) | (read6502(0xFFFB) << 8))

def irq6502():
    global cpustatus, pc, FLAG_INTERRUPT
    push16(pc)
    push8(cpustatus)
    cpustatus |= FLAG_INTERRUPT
    cpustatus &= 0xFF
    pc = (read6502(0xFFFE) | (read6502(0xFFFF) << 8))


def exec6502(tickcount):
    global opcode, cpustatus, useaccum, pc, FLAG_CONSTANT

    while tickcount > 0:
        tickcount -= 1
        pc &= 0xFFFF
        
        opcode = read6502(pc)
        pc += 1
        cpustatus |= FLAG_CONSTANT
        useaccum = 0

        if opcode == 0x0:
            imp()
            brk()
        elif opcode == 0x1:
            indx()
            ora()
        elif opcode == 0x5:
            zp()
            ora()
        elif opcode == 0x6:
            zp()
            asl()
        elif opcode == 0x8:
            imp()
            php()
        elif opcode == 0x9:
            imm()
            ora()
        elif opcode == 0xA:
            acc()
            asl()
        elif opcode == 0xD:
            abso()
            ora()
        elif opcode == 0xE:
            abso()
            asl()
        elif opcode == 0x10:
            rel()
            bpl()
        elif opcode == 0x11:
            indy()
            ora()
        elif opcode == 0x15:
            zpx()
            ora()
        elif opcode == 0x16:
            zpx()
            asl()
        elif opcode == 0x18:
            imp()
            clc()
        elif opcode == 0x19:
            absy()
            ora()
        elif opcode == 0x1D:
            absx()
            ora()
        elif opcode == 0x1E:
            absx()
            asl()
        elif opcode == 0x20:
            abso()
            jsr()
        elif opcode == 0x21:
            indx()
            op_and()
        elif opcode == 0x24:
            zp()
            op_bit()
        elif opcode == 0x25:
            zp()
            op_and()
        elif opcode == 0x26:
            zp()
            rol()
        elif opcode == 0x28:
            imp()
            plp()
        elif opcode == 0x29:
            imm()
            op_and()
        elif opcode == 0x2A:
            acc()
            rol()
        elif opcode == 0x2C:
            abso()
            op_bit()
        elif opcode == 0x2D:
            abso()
            op_and()
        elif opcode == 0x2E:
            abso()
            rol()
        elif opcode == 0x30:
            rel()
            bmi()
        elif opcode == 0x31:
            indy()
            op_and()
        elif opcode == 0x35:
            zpx()
            op_and()
        elif opcode == 0x36:
            zpx()
            rol()
        elif opcode == 0x38:
            imp()
            sec()
        elif opcode == 0x39:
            absy()
            op_and()
        elif opcode == 0x3D:
            absx()
            op_and()
        elif opcode == 0x3E:
            absx()
            rol()
        elif opcode == 0x40:
            imp()
            rti()
        elif opcode == 0x41:
            indx()
            eor()
        elif opcode == 0x45:
            zp()
            eor()
        elif opcode == 0x46:
            zp()
            lsr()
        elif opcode == 0x48:
            imp()
            pha()
        elif opcode == 0x49:
            imm()
            eor()
        elif opcode == 0x4A:
            acc()
            lsr()
        elif opcode == 0x4C:
            abso()
            jmp()
			
        elif opcode == 0x4D:
            abso()
            eor()
        
        elif opcode == 0x4E:
            abso()
            lsr()
        
        elif opcode == 0x50:
            rel()
            bvc()
        
        elif opcode == 0x51:
            indy()
            eor()
        
        elif opcode == 0x55:
            zpx()
            eor()
            
        elif opcode == 0x56:
            zpx()
            lsr()
            
        elif opcode == 0x58:
            imp()
            cli()
            
        elif opcode == 0x59:
            absy()
            eor()
            
        elif opcode == 0x5D:
            absx()
            eor()
            
        elif opcode == 0x5E:
            absx()
            lsr()
            
        elif opcode == 0x60:
            imp()
            rts()
            
        elif opcode == 0x61:
            indx()
            adc()
            
        elif opcode == 0x65:
            zp()
            adc()
            
        elif opcode == 0x66:
            zp()
            ror()
            
        elif opcode == 0x68:
            imp()
            pla()
            
        elif opcode == 0x69:
            imm()
            adc()
            
        elif opcode == 0x6A:
            acc()
            ror()
            
        elif opcode == 0x6C:
            ind()
            jmp()
            
        elif opcode == 0x6D:
            abso()
            adc()
            
        elif opcode == 0x6E:
            abso()
            ror()
            
        elif opcode == 0x70:
            rel()
            bvs()
            
        elif opcode == 0x71:
            indy()
            adc()
            
        elif opcode == 0x75:
            zpx()
            adc()
            
        elif opcode == 0x76:
            zpx()
            ror()
            
        elif opcode == 0x78:
            imp()
            sei()
            
        elif opcode == 0x79:
            absy()
            adc()
            
        elif opcode == 0x7D:
            absx()
            adc()
            
        elif opcode == 0x7E:
            absx()
            ror()
            
        elif opcode == 0x81:
            indx()
            sta()
            
        elif opcode == 0x84:
            zp()
            sty()
            
        elif opcode == 0x85:
            zp()
            sta()
            
        elif opcode == 0x86:
            zp()
            stx()
            
        elif opcode == 0x88:
            imp()
            dey()
            
        elif opcode == 0x8A:
            imp()
            txa()
            
        elif opcode == 0x8C:
            abso()
            sty()
            
        elif opcode == 0x8D:
            abso()
            sta()
            
        elif opcode == 0x8E:
            abso()
            stx()
            
        elif opcode == 0x90:
            rel()
            bcc()
            
        elif opcode == 0x91:
            indy()
            sta()
            
        elif opcode == 0x94:
            zpx()
            sty()
            
        elif opcode == 0x95:
            zpx()
            sta()
            
        elif opcode == 0x96:
            zpy()
            stx()
            
        elif opcode == 0x98:
            imp()
            tya()
            
        elif opcode == 0x99:
            absy()
            sta()
            
        elif opcode == 0x9A:
            imp()
            txs()
            
        elif opcode == 0x9D:
            absx()
            sta()
            
        elif opcode == 0xA0:
            imm()
            ldy()
            
        elif opcode == 0xA1:
            indx()
            lda()
            
        elif opcode == 0xA2:
            imm()
            ldx()
            
        elif opcode == 0xA4:
            zp()
            ldy()
            
        elif opcode == 0xA5:
            zp()
            lda()
            
        elif opcode == 0xA6:
            zp()
            ldx()
            
        elif opcode == 0xA8:
            imp()
            tay()
            
        elif opcode == 0xA9:
            imm()
            lda()
            
        elif opcode == 0xAA:
            imp()
            tax()
            
        elif opcode == 0xAC:
            abso()
            ldy()
            
        elif opcode == 0xAD:
            abso()
            lda()
            
        elif opcode == 0xAE:
            abso()
            ldx()
            
        elif opcode == 0xB0:
            rel()
            bcs()
            
        elif opcode == 0xB1:
            indy()
            lda()
            
        elif opcode == 0xB4:
            zpx()
            ldy()
            
        elif opcode == 0xB5:
            zpx()
            lda()
            
        elif opcode == 0xB6:
            zpy()
            ldx()
            
        elif opcode == 0xB8:
            imp()
            clv()
            
        elif opcode == 0xB9:
            absy()
            lda()
            
        elif opcode == 0xBA:
            imp()
            tsx()
            
        elif opcode == 0xBC:
            absx()
            ldy()
            
        elif opcode == 0xBD:
            absx()
            lda()
            
        elif opcode == 0xBE:
            absy()
            ldx()
            
        elif opcode == 0xC0:
            imm()
            cpy()
            
        elif opcode == 0xC1:
            indx()
            cmp()
            
        elif opcode == 0xC4:
            zp()
            cpy()
            
        elif opcode == 0xC5:
            zp()
            cmp()
            
        elif opcode == 0xC6:
            zp()
            dec()
            
        elif opcode == 0xC8:
            imp()
            iny()
            
        elif opcode == 0xC9:
            imm()
            cmp()
            
        elif opcode == 0xCA:
            imp()
            dex()
            
        elif opcode == 0xCC:
            abso()
            cpy()
            
        elif opcode == 0xCD:
            abso()
            cmp()
            
        elif opcode == 0xCE:
            abso()
            dec()
            
        elif opcode == 0xD0:
            rel()
            bne()
            
        elif opcode == 0xD1:
            indy()
            cmp()
            
        elif opcode == 0xD5:
            zpx()
            cmp()
            
        elif opcode == 0xD6:
            zpx()
            dec()
            
        elif opcode == 0xD8:
            imp()
            cld()
            
        elif opcode == 0xD9:
            absy()
            cmp()
            
        elif opcode == 0xDD:
            absx()
            cmp()
            
        elif opcode == 0xDE:
            absx()
            dec()
            
        elif opcode == 0xE0:
            imm()
            cpx()
            
        elif opcode == 0xE1:
            indx()
            sbc()
            
        elif opcode == 0xE4:
            zp()
            cpx()
            
        elif opcode == 0xE5:
            zp()
            sbc()
            
        elif opcode == 0xE6:
            zp()
            inc()
            
        elif opcode == 0xE8:
            imp()
            inx()
            
        elif opcode == 0xE9:
            imm()
            sbc()
            
        elif opcode == 0xEB:
            imm()
            sbc()
            
        elif opcode == 0xEC:
            abso()
            cpx()
            
        elif opcode == 0xED:
            abso()
            sbc()
            
        elif opcode == 0xEE:
            abso()
            inc()
            
        elif opcode == 0xF0:
            rel()
            beq()
            
        elif opcode == 0xF1:
            indy()
            sbc()
            
        elif opcode == 0xF5:
            zpx()
            sbc()
            
        elif opcode == 0xF6:
            zpx()
            inc()
            
        elif opcode == 0xF8:
            imp()
            sed()
            
        elif opcode == 0xF9:
            absy()
            sbc()
            
        elif opcode == 0xFD:
            absx()
            sbc()
            
        elif opcode == 0xFE:
            absx()
            inc()
            
    





      

def writeVIDEO(address, data):
    charptr,x, y = (2048 + (data << 3)),((address % 40) << 3), ((address // 40) << 3)
    window = pygame.Rect(x*2, y*2, 16, 16)
    subsurface = screen.subsurface(window)
    for c in range(8):
        row = charROM[charptr]
        for r in range(8):
            subsurface.fill((255,255,255) if row & (128 >> r) else (0,0,0), (r*2, c*2, 2, 2))
        charptr += 1
    




                    




# Initialize the text input and output strings
inputS =""
input_str=""
caps_lock = False
screen = pygame.display.set_mode((640, 400))

pygame.init()
screen.fill((0, 0, 0))


ser=serial.Serial('/dev/pts/2', 115200)
reset6502()
t=0

while True:
    exec6502(10)
    writeVIDEO(t, videomem[t])
    t=t+1
    
    if t > 999:
        t=0
        pygame.display.update()
    if ser.in_waiting > 0:
    # read a byte from the serial port
        key = ser.read(1)
        curkey=int.from_bytes(key, "big")
    for event in pygame.event.get():
      if event.type == pygame.QUIT:
            # Quit the game if the user closes the window
            pygame.quit()
            quit()
      elif event.type == pygame.KEYDOWN:
            # Handle modifier keys
            if event.key == pygame.K_LSHIFT or event.key == pygame.K_RSHIFT:
                inputS += "<SHIFT>"
            elif event.key == pygame.K_LCTRL or event.key == pygame.K_RCTRL:
                inputS += "<CTRL>"
            elif event.key == pygame.K_LALT or event.key == pygame.K_RALT:
                inputS += "<ALT>"
            elif event.key == pygame.K_BACKSPACE:
                input_str = input_str[:-1]
                curkey=8
            elif event.key == pygame.K_CAPSLOCK:
                caps_lock = not caps_lock
            else:
                # Add the character to the input string, and toggle case if needed
                char = event.unicode
                if caps_lock or (pygame.key.get_mods() & pygame.KMOD_SHIFT):
                    char = char.upper()
                #input_str += char
                curkey = ord(char)
