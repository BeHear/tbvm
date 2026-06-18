import os
import io
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

from assembler import Assembler, AssembleError

TOKEN = os.environ.get("TBVM_BOT_TOKEN", "")
asm = Assembler()

HELP_TEXT = """\
🤖 *TBVM Assembler Bot*

Преобразует текст программы в байткод для Tiny Basic VM.

*Команды:*
/asm \\(код\\) — собрать программу, получить \\#\\.bin
/help — список инструкций
/example — пример программы

*Доступные инструкции:*

`HALT` — останов
`MOV rN val` — rN \\= val
`ADD rN rM` — rN \\+= regs\\[rM\\]
`ADDI rN val` — rN \\+= val
`SUB rN rM` — rN \\-= regs\\[rM\\]
`SUBI rN val` — rN \\-= val
`CMP rN rM` — flag \\= \\(rN \\=\\= rM\\)
`CMPI rN val` — flag \\= \\(rN \\=\\= val\\)
`JMP addr` — прыжок
`JZ addr` — прыжок если flag
`JNZ addr` — прыжок если !flag
`CALL addr` — вызов подпрограммы
`RET` — возврат
`STORE addr rN` — memory\\[addr\\] \\= rN
`LOAD rN addr` — rN \\= memory\\[addr\\]
`DRAW rX rY rC` — пиксель в \\(regs\\[rX\\], regs\\[rY\\) цвета regs\\[rC\\]
`PRINT rN` — вывод regs\\[rN\\]

*Синтаксис:*
Метки: \\.имя
Комментарии: \\; или \\#
Регистры: r0\\-r7"""

EXAMPLE_CODE = """\
; Countdown from 10 to 1
MOV r0 10
.loop
PRINT r0
SUBI r0 1
CMPI r0 0
JNZ .loop
HALT"""


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 *TBVM Assembler Bot*\n\n"
        "Ассемблирует программы для Tiny Basic Virtual Machine.\n\n"
        "`/help` — справка\n"
        "`/asm MOV r0 42 ; PRINT r0 ; HALT` — собрать\n"
        "`/example` — пример\n\n"
        "📁 *Загрузи `.s` или `.asm` файл* — получу `.bin`"
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown_v2(HELP_TEXT)


async def cmd_asm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not ctx.args:
        await update.message.reply_text(
            "Использование: `/asm MOV r0 42 ; PRINT r0 ; HALT`\n"
            "Можно разделять строки через `;` или многострочным сообщением."
        )
        return
    code = ' '.join(ctx.args).replace(';', '\n')
    try:
        data = asm.assemble(code)
        caption = f"✅ Собрано: {len(data)} bytes ({len(data)//4} instructions)"
        await update.message.reply_document(
            document=io.BytesIO(data),
            filename="program.bin",
            caption=caption,
        )
        dis = asm.disassemble(data)
        if len(dis) < 3500:
            await update.message.reply_text(f"```\n{dis}\n```")
    except AssembleError as e:
        await update.message.reply_text(f"❌ {e}")
    except Exception as e:
        await update.message.reply_text(f"❌ Internal error: {e}")


SUPPORTED_EXTENSIONS = {'.s', '.asm', '.txt'}


async def handle_file(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    doc = update.message.document
    if not doc:
        return

    ext = os.path.splitext(doc.file_name or "")[1].lower()
    if ext not in SUPPORTED_EXTENSIONS:
        allowed = ", ".join(SUPPORTED_EXTENSIONS)
        await update.message.reply_text(
            f"❌ Поддерживаются только файлы: {allowed}"
        )
        return

    msg = await update.message.reply_text("⏳ Ассемблирую...")
    try:
        file = await doc.get_file()
        raw = await file.download_as_bytearray()
        code = raw.decode("utf-8")
    except Exception:
        await msg.edit_text("❌ Не удалось прочитать файл. Убедись, что он в UTF-8.")
        return

    try:
        data = asm.assemble(code)
        base = os.path.splitext(os.path.basename(doc.file_name))[0]
        # Strip any path traversal characters from the base name
        base = "".join(c for c in base if c.isalnum() or c in "._- ")
        if not base:
            base = "program"
        caption = f"✅ {doc.file_name} → {base}.bin ({len(data)} bytes, {len(data)//4} instr)"
        await update.message.reply_document(
            document=io.BytesIO(data),
            filename=f"{base}.bin",
            caption=caption,
        )
        await msg.delete()
        dis = asm.disassemble(data)
        if len(dis) < 3500:
            await update.message.reply_text(f"```\n{dis}\n```")
    except AssembleError as e:
        await msg.edit_text(f"❌ {e}")
    except Exception as e:
        await msg.edit_text(f"❌ Internal error: {e}")


async def cmd_example(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    data = asm.assemble(EXAMPLE_CODE)
    await update.message.reply_document(
        document=io.BytesIO(data),
        filename="countdown.bin",
        caption=f"📄 Обратный отсчёт от 10 ({len(data)} bytes)",
    )
    dis = asm.disassemble(data)
    await update.message.reply_text(f"*Исходник:*\n```\n{EXAMPLE_CODE.strip()}\n```\n*Байткод:*\n```\n{dis}\n```")


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    if not TOKEN:
        print("❌ Укажите токен: export TBVM_BOT_TOKEN=ваш_токен")
        return
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("asm", cmd_asm))
    app.add_handler(CommandHandler("example", cmd_example))
    app.add_handler(MessageHandler(filters.Document.FileExtension("s"), handle_file))
    app.add_handler(MessageHandler(filters.Document.FileExtension("asm"), handle_file))
    app.add_handler(MessageHandler(filters.Document.FileExtension("txt"), handle_file))
    print("✅ TBVM Bot запущен")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
