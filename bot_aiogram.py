import asyncio
import io
import logging
import os

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message

from assembler import Assembler, AssembleError

TOKEN = os.environ.get("TBVM_BOT_TOKEN", "")
asm = Assembler()

HELP_TEXT = """\
🤖 <b>TBVM Assembler Bot</b>

Преобразует текст программы в байткод для Tiny Basic VM.

<b>Команды:</b>
/asm &lt;код&gt; — собрать программу, получить .bin
/help — список инструкций
/example — пример программы
📁 Загрузи .s / .asm / .txt файл — получу .bin

<b>Инструкции:</b>
<code>HALT</code> — останов
<code>MOV rN val</code> — rN = val
<code>ADD rN rM</code> — rN += regs[rM]
<code>ADDI rN val</code> — rN += val
<code>SUB rN rM</code> — rN -= regs[rM]
<code>SUBI rN val</code> — rN -= val
<code>CMP rN rM</code> — flag = (rN == rM)
<code>CMPI rN val</code> — flag = (rN == val)
<code>JMP addr</code> — прыжок
<code>JZ addr</code> — прыжок если flag
<code>JNZ addr</code> — прыжок если !flag
<code>CALL addr</code> — вызов подпрограммы
<code>RET</code> — возврат
<code>STORE addr rN</code> — memory[addr] = rN
<code>LOAD rN addr</code> — rN = memory[addr]
<code>DRAW rX rY rC</code> — пиксель (regs[rX], regs[rY]) цвета regs[rC]
<code>PRINT rN</code> — вывод regs[rN]

<b>Синтаксис:</b>
Метки: <code>.имя</code>
Комментарии: <code>;</code> или <code>#</code>
Регистры: <code>r0</code>-<code>r7</code>
Разделитель строк: <code>;</code>"""

EXAMPLE_CODE = """\
; Countdown from 10 to 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT"""

SUPPORTED_EXT = (".s", ".asm", ".txt")
MAX_FILE_SIZE = 64 * 1024

dp = Dispatcher()


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "🤖 <b>TBVM Assembler Bot</b>\n\n"
        "Ассемблирует программы для Tiny Basic Virtual Machine.\n\n"
        "<code>/help</code> — справка\n"
        "<code>/asm MOV r0 42 ; PRINT r0 ; HALT</code> — собрать\n"
        "<code>/example</code> — пример\n\n"
        "📁 <b>Загрузи</b> <code>.s</code> / <code>.asm</code> / <code>.txt</code> файл — получу <code>.bin</code>",
    )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT)


@dp.message(Command("example"))
async def cmd_example(message: Message) -> None:
    data = asm.assemble(EXAMPLE_CODE)
    dis = asm.disassemble(data)
    await message.answer_document(
        document=BufferedInputFile(data, filename="countdown.bin"),
        caption=f"📄 Обратный отсчёт от 10 ({len(data)} bytes)",
    )
    if len(dis) < 3500:
        await message.answer(f"<b>Исходник:</b>\n<pre>{EXAMPLE_CODE.strip()}</pre>\n<b>Байткод:</b>\n<pre>{dis}</pre>")


@dp.message(Command("asm"))
async def cmd_asm(message: Message, command: CommandObject) -> None:
    args = command.args
    if not args:
        await message.answer(
            "Использование: <code>/asm MOV r0 42 ; PRINT r0 ; HALT</code>\n"
            "Можно разделять строки через <code>;</code> или многострочным сообщением."
        )
        return

    code = args.replace(";", "\n")
    try:
        data = asm.assemble(code)
        dis = asm.disassemble(data)
        caption = f"✅ Собрано: {len(data)} bytes ({len(data)//4} instructions)"
        await message.answer_document(
            document=BufferedInputFile(data, filename="program.bin"),
            caption=caption,
        )
        if len(dis) < 3500:
            await message.answer(f"<pre>{dis}</pre>")
    except AssembleError as e:
        await message.answer(f"❌ {e}")
    except Exception as e:
        await message.answer(f"❌ Internal error: {e}")


@dp.message(F.document)
async def handle_file(message: Message, bot: Bot) -> None:
    doc = message.document
    if not doc or not doc.file_name:
        return

    ext = os.path.splitext(doc.file_name)[1].lower()
    if ext not in SUPPORTED_EXT:
        await message.answer(f"❌ Поддерживаются только: {', '.join(SUPPORTED_EXT)}")
        return

    if doc.file_size and doc.file_size > MAX_FILE_SIZE:
        await message.answer(f"❌ Файл слишком большой (макс. {MAX_FILE_SIZE // 1024} KB)")
        return

    msg = await message.answer("⏳ Ассемблирую...")
    try:
        file = await bot.get_file(doc.file_id)
        raw = await bot.download_file(file.file_path)
        code = raw.read().decode("utf-8")
    except Exception:
        await msg.edit_text("❌ Не удалось прочитать файл. Убедись, что он в UTF-8.")
        return

    try:
        data = asm.assemble(code)
        base = os.path.splitext(os.path.basename(doc.file_name))[0]
        base = "".join(c for c in base if c.isalnum() or c in "._- ")
        if not base:
            base = "program"
        caption = f"✅ {doc.file_name} → {base}.bin ({len(data)} bytes, {len(data)//4} instr)"
        await message.answer_document(
            document=BufferedInputFile(data, filename=f"{base}.bin"),
            caption=caption,
        )
        await msg.delete()
        dis = asm.disassemble(data)
        if len(dis) < 3500:
            await message.answer(f"<pre>{dis}</pre>")
    except AssembleError as e:
        await msg.edit_text(f"❌ {e}")
    except Exception as e:
        await msg.edit_text(f"❌ Internal error: {e}")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not TOKEN:
        print("❌ Укажите токен: export TBVM_BOT_TOKEN=ваш_токен")
        return

    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
