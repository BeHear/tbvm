# TBVM — Telegram Bot Virtual Machine

Экспериментальная виртуальная машина с минимальным набором инструкций, графическим выводом (128×128 VRAM, экспорт в PNG) и ассемблером. Ядро написано на **Rust** с нулевым `unsafe` кодом.

## Возможности

- **8 регистров** (r0–r7), **1024 слова** памяти, **256 вызовов** стека
- **26 инструкций**: MOV, ADD/ADDI, SUB/SUBI, CMP/CMPI, JMP/JZ/JNZ, CALL/RET, STORE/LOAD, DRAW, PRINT, HALT, CLS, RAND, KEY, INT/IRET, CLI/STI, SETMODE, EXIT, TIMER
- **Графический вывод** 128×128 пикселей в **PNG** через инструкцию `DRAW`. Цвет кодируется как `0xRRGGBB` (битовая маска). После выполнения программы VRAM автоматически экспортируется в `output.png`.
- **Rust VM** — type-safe, zero `unsafe`, гарантированная защита памяти на уровне компилятора
- **Режимы kernel/user** — защищённые инструкции, IVT, INT/IRET, таймер — можно писать свою ОС
- **Ассемблер** (Python) — из текста в байткод и обратно
- **Telegram бот** — пиши программы прямо из мессенджера
- **[Полная документация](documentation.md)** — архитектура ВМ, система команд, бинарный формат, примеры

## Быстрый старт

```bash
# Сборка
make

# Ассемблирование и исполнение одной строкой
python3 -c "
from assembler import Assembler
a = Assembler()
data = a.assemble('MOV r0 42\nPRINT r0\nHALT')
open('program.bin', 'wb').write(data)
"

./tbvm run program.bin      # → OUT: 42
```

После выполнения программ с `DRAW` появится файл `output.png` — кадровый буфер 128×128.

## Инструкции

### Основные

| Инструкция | Описание | Слов |
|-----------|----------|------|
| `HALT` | Останов | 1 |
| `MOV rN val` | `rN = val` | 3 |
| `ADD rN rM` | `rN += regs[rM]` | 3 |
| `ADDI rN val` | `rN += val` | 3 |
| `SUB rN rM` | `rN -= regs[rM]` | 3 |
| `SUBI rN val` | `rN -= val` | 3 |
| `CMP rN rM` | `flag = (rN == rM)` | 3 |
| `CMPI rN val` | `flag = (rN == val)` | 3 |
| `JMP addr` | Безусловный переход | 2 |
| `JZ addr` | Переход если flag | 2 |
| `JNZ addr` | Переход если !flag | 2 |
| `CALL addr` | Вызов подпрограммы | 2 |
| `RET` | Возврат | 1 |

### Память, графика, ввод-вывод

| Инструкция | Описание | Слов |
|-----------|----------|------|
| `STORE addr rN` | `memory[addr] = rN` | 3 |
| `LOAD rN addr` | `rN = memory[addr]` | 3 |
| `DRAW rX rY rC` | Пиксель `(regs[rX], regs[rY])` цвета `regs[rC]` (см. цветовую схему) | 4 |
| `PRINT rN` | Вывод `OUT: regs[rN]` в stdout | 2 |
| `CLS` | Заливка VRAM чёрным (`0x000000`) | 1 |
| `RAND rN mod` | `rN = rand() % mod` (LCG) | 3 |
| `KEY rN` | Чтение ASCII-кода клавиши (блокирующее) | 2 |

### Системные (поддержка ОС)

| Инструкция | Описание | Слов |
|-----------|----------|------|
| `INT vec` | Программное прерывание | 2 |
| `IRET` | Возврат из прерывания | 1 |
| `CLI` | Запретить прерывания | 1 |
| `STI` | Разрешить прерывания | 1 |
| `SETMODE rN` | Установить режим: 0=kernel, 1=user | 2 |
| `EXIT rN` | Останов с кодом `regs[rN]` | 2 |
| `TIMER n` | Интервал таймера (n инструкций, 0=выкл) | 2 |

### Цветовая схема DRAW

Цвет пикселя задаётся 32-битным целым значением в регистре. Маска (RGB):

```
0xRRGGBB
  └┬┘└┬┘└┬┘
   R  G  B
```

Примеры:
- `0xFF0000` — красный
- `0x00FF00` — зелёный
- `0x0000FF` — синий
- `0xFFFFFF` — белый
- `0x000000` — чёрный

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
; Сумма чисел от 1 до 10 → OUT: 55
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
MOV r0 0       ; x
MOV r1 0       ; y
MOV r2 255     ; цвет: 0x0000FF (синий)
.loop
DRAW r0 r1 r2
ADDI r0 1
ADDI r1 1
CMPI r0 64
JNZ .loop
HALT
; После выполнения: output.png с синей диагональю
```

## Telegram бот

Позволяет ассемблировать программы в байткод TBVM прямо из Telegram, выполнять их в изолированной песочнице и получать `.bin` / `.png`.

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
| `/help` | Справка по всем инструкциям |
| `/asm <code>` | Собрать → `program.bin` |
| `/run <code>` | Собрать, выполнить в песочнице → stdout + `output.png` |
| `/example` | Пример countdown.bin |
| Загрузка `.s`/`.asm`/`.txt` | Ассемблирование файла |

При выполнении `/run` бот запускает ВМ в изолированном окружении:
- `TemporaryDirectory` (автоудаление)
- `setrlimit(RLIMIT_AS=64MB, RLIMIT_CPU=3s)` — лимит памяти и CPU
- Таймаут 3 секунды
- Рейт-лимит 5 секунд на пользователя
- `O_NOFOLLOW` для защиты от symlink-атак

Если программа использует `DRAW`, бот пришлёт `output.png` отдельным сообщением.

## CLI

```bash
# Исполнение (полная ВМ, 26 инструкций)
./tbvm run program.bin

# Дизассемблирование
./tbvm disasm program.bin

# Изолированный запуск shell-команд
./tbvm isolate program.bin /tmp/sandbox_dir
```

## Поддержка ОС

TBVM поддерживает два режима привилегий, таблицу векторов прерываний (IVT) в памяти, инструкции INT/IRET/CLI/STI/SETMODE/EXIT/TIMER и аппаратные fault-ы (invalid opcode, privilege violation, timer). Можно реализовать полноценную ОС с системными вызовами, защищёнными инструкциями и прерываниями по таймеру.

**Стандартные векторы:**
| Вектор | Назначение |
|--------|------------|
| 0 | Invalid opcode |
| 1 | Privilege violation |
| 2 | Memory bounds |
| 3 | Timer interrupt |
| 4+ | Пользовательские (`INT n`) |

## Сборка и тестирование

```bash
make              # cargo build --release → ./tbvm
make clean        # удалить бинарник + output.png

python3 test_bot.py    # 42 теста: ассемблер, песочница, графика
```

## Структура проекта

```
tbvm/
├── assembler.py         # Ассемблер / дизассемблер
├── bot_aiogram.py       # Telegram бот (aiogram 3.x)
├── bot.py               # Telegram бот (python-telegram-bot, легаси)
├── test_bot.py          # 42 теста
├── documentation.md     # Полная архитектурная документация
├── Makefile             # Сборка Rust
├── rust/
│   ├── Cargo.toml       # Зависимости: image, libc
│   └── src/
│       ├── main.rs      # CLI (run / isolate / disasm)
│       ├── vm.rs        # VM engine: 26 инструкций, VRAM, PNG-экспорт
│       ├── sandbox.rs   # Изолированное выполнение (fork + setrlimit)
│       └── error.rs     # VmError: все типы ошибок ВМ
├── programs/
│   ├── countdown.s      # Обратный отсчёт 10→1
│   ├── math.s           # Сумма 1..10
│   └── demo.s           # Диагональная линия
└── requirements.txt     # aiogram>=3.0
```

## Лицензия

MIT
