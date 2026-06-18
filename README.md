# TBVM — Telegram Bot Virtual Machine

Экспериментальная виртуальная машина с минимальным набором инструкций, графическим выводом (128×128 VRAM, PPM) и ассемблером. Ядро написано на **Rust** с нулевым `unsafe` кодом.

## Возможности

- **8 регистров** (r0–r7), **1024 слова** памяти, **256 вызовов** стека
- **17 инструкций**: MOV, ADD/ADDI, SUB/SUBI, CMP/CMPI, JMP/JZ/JNZ, CALL/RET, STORE/LOAD, DRAW, PRINT, HALT, CLS, RAND, KEY
- **Графический вывод** 128×128 пикселей в PPM (портлет) через инструкцию DRAW
- **Rust VM** — type-safe, zero `unsafe`, гарантированная защита памяти на уровне компилятора
- **Режимы kernel/user** — защищённые инструкции, IVT, INT/IRET, таймер — можно писать свою ОС
- **Ассемблер** (Python) — превращает текст в байткод
- **Telegram бот** — создание программ прямо из мессенджера
- **[Документация](documentation.md)** — полный справочник по архитектуре ВМ

## Быстрый старт

```bash
# Сборка
make

# Ассемблирование
python3 -c "
from assembler import Assembler
a = Assembler()
data = a.assemble('MOV r0 42\\nPRINT r0\\nHALT')
open('program.bin', 'wb').write(data)
"

# Исполнение
./tbvm run program.bin
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
| `CLS` | Очистка VRAM |
| `RAND rN mod` | rN = случайное число 0..mod-1 |
| `KEY rN` | Чтение клавиши (ASCII) в rN |
| `INT vec` | Программное прерывание `vec` |
| `IRET` | Возврат из прерывания |
| `CLI` | Запретить прерывания |
| `STI` | Разрешить прерывания |
| `SETMODE rN` | Установить режим (0=kernel, 1=user) |
| `EXIT rN` | Останов с кодом `regs[N]` |
| `TIMER n` | Установить интервал таймера (n инструкций) |

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

Позволяет ассемблировать программы в байткод TBVM прямо из Telegram, выполнять их в песочнице и получать `.bin` файл.

### Установка и запуск

```bash
pip install -r requirements.txt
export TBVM_BOT_TOKEN=ваш_токен
python bot_aiogram.py
```

### Команды бота

| Команда | Что делает |
|---------|-----------|
| `/start` | Приветствие |
| `/help` | Справка по всем 17 инструкциям |
| `/asm <code>` | Собрать → program.bin |
| `/run <code>` | Собрать и выполнить в песочнице |
| `/example` | Пример программы |

## CLI

```bash
# Исполнение
./tbvm run program.bin

# Дизассемблирование
./tbvm disasm program.bin

# Изолированный запуск (для shell-команд)
./tbvm isolate program.bin /tmp/sandbox_dir
```

### Поддержка ОС

TBVM поддерживает режимы kernel/user, таблицу векторов прерываний (IVT) в памяти,
инструкции INT/IRET/CLI/STI/SETMODE/EXIT/TIMER и fault-ы (invalid opcode,
privilege violation, timer). Можно реализовать простое ОС с системными вызовами,
защитой памяти (по адресам) и прерываниями по таймеру.

## Структура проекта

```
tbvm/
├── assembler.py       # Ассемблер/дизассемблер
├── bot_aiogram.py     # Telegram бот (aiogram)
├── bot.py             # Telegram бот (python-telegram-bot, легаси)
├── test_bot.py        # Тесты
├── Makefile           # Сборка Rust
├── rust/              # Rust VM (ядро)
│   ├── Cargo.toml
│   └── src/
│       ├── main.rs    # CLI (run, isolate, disasm)
│       ├── vm.rs      # VM engine (type-safe)
│       ├── sandbox.rs # Песочница (fork + setrlimit)
│       └── error.rs   # VmError
├── programs/          # Примеры программ
└── requirements.txt
```

## Лицензия

MIT
