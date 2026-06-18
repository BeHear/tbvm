# TBVM — Tiny Basic Virtual Machine

Экспериментальная виртуальная машина с минимальным набором инструкций, графическим выводом (128×128 VRAM, PPM) и ассемблером.

## Возможности

- **8 регистров** (r0–r7), **1024 слова** памяти, **256 вызовов** стека
- **17 инструкций**: MOV, ADD/ADDI, SUB/SUBI, CMP/CMPI, JMP/JZ/JNZ, CALL/RET, STORE/LOAD, DRAW, PRINT, HALT
- **Графический вывод** 128×128 пикселей в PPM (портлет) через инструкцию DRAW
- **Изолированный движок** (`iso_engine.c`) для Windows с песочницей через Job Object
- **Ассемблер** (Python) — превращает текст в байткод
- **Telegram бот** — создание программ прямо из мессенджера

## Быстрый старт

```bash
# Сборка VM
make

# Ассемблирование программы
python3 -c "
from assembler import Assembler
a = Assembler()
data = a.assemble('MOV r0 42\\nPRINT r0\\nHALT')
open('program.bin', 'wb').write(data)
"

# Запуск
./vm program.bin
```

## Инструкции

| Инструкция | Описание |
|-----------|----------|
| `HALT` | Останов |
| `MOV rN val` | rN = val |
| `ADD rN rM` | rN += regs[rM] |
| `ADDI rN val` | rN += val |
| `SUB rN rM` | rN -= regs[rM] |
| `SUBI rN val` | rN -= val |
| `CMP rN rM` | flag = (rN == rM) |
| `CMPI rN val` | flag = (rN == val) |
| `JMP addr` | Безусловный прыжок |
| `JZ addr` | Прыжок если flag == 1 |
| `JNZ addr` | Прыжок если flag == 0 |
| `CALL addr` | Вызов подпрограммы |
| `RET` | Возврат |
| `STORE addr rN` | memory[addr] = rN |
| `LOAD rN addr` | rN = memory[addr] |
| `DRAW rX rY rC` | Пиксель в (regs[rX], regs[rY]) цвета regs[rC] |
| `PRINT rN` | Вывод regs[rN] |

## Примеры

```asm
; Обратный отсчёт от 10 до 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT
```

```asm
; Сумма чисел от 1 до 10
MOV r0 10
MOV r1 0
.loop
ADD r1 r0
SUBI r0 1
CMPI r0 0
JNZ .loop
PRINT r1
HALT
```

```asm
; Диагональная линия (графика)
MOV r0 0
MOV r1 0
MOV r2 255
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
HALT
```

## Telegram бот

Позволяет ассемблировать программы прямо из Telegram.

```bash
pip install -r requirements.txt
export TBVM_BOT_TOKEN=ваш_токен
python bot.py
```

Команды: `/asm <код>`, `/help`, `/example`, `/start`

## Структура проекта

```
tbvm/
├── vm.c            # Основная VM (кросс-платформенная)
├── iso_engine.c    # VM с Windows-песочницей
├── assembler.py    # Ассемблер/дизассемблер
├── bot.py          # Telegram бот
├── Makefile        # Сборка
├── programs/       # Примеры программ
└── requirements.txt
```

## Лицензия

MIT
