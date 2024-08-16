import nest_asyncio
from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, CallbackContext
import asyncio
import openpyxl
from openpyxl import Workbook
import os

nest_asyncio.apply()

TOKEN = '7451895193:AAE2MW1dR1gICWutcn0-ijpaKxMyM59ajWo'
EXCEL_FILE = 'user_responses.xlsx'

bot = Bot(token=TOKEN)

# ذخیره کدهای غذای روز و غذای رایگان
daily_food_codes = ['CODE1', 'CODE2', 'CODE3', 'CODE4', 'CODE5', 'CODE6', 'CODE7', 'CODE8', 'CODE9', 'CODE10']
free_food_codes = ['FREE1', 'FREE2', 'FREE3', 'FREE4', 'FREE5', 'FREE6', 'FREE7', 'FREE8', 'FREE9', 'FREE10']

admin_chat_id = '5440267671'  # آیدی ادمین برای تایید واریز

user_data = {}
pending_payment_messages = {}  # ذخیره پیام‌های در حال انتظار برای تایید

def initialize_excel_file():
    if not os.path.exists(EXCEL_FILE):
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = 'User Responses'
        sheet.append(['Chat ID', 'Student ID', 'Password', 'Used University Food', 'Approval Status', 'Payment Status', 'Free Food Code'])
        workbook.save(EXCEL_FILE)

initialize_excel_file()

async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_data[chat_id] = {'state': 'waiting_for_id'}
    await context.bot.send_message(chat_id=chat_id, text="لطفاً شماره دانشجویی خود را وارد کنید:")

async def handle_message(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    state = user_data.get(chat_id, {}).get('state')

    if state == 'waiting_for_id':
        user_data[chat_id]['student_id'] = update.message.text
        user_data[chat_id]['state'] = 'waiting_for_password'
        await context.bot.send_message(chat_id=chat_id, text="شماره دانشجویی ثبت شد. لطفاً رمز ورود به سامانه غذا را وارد کنید:")

    elif state == 'waiting_for_password':
        user_data[chat_id]['password'] = update.message.text
        user_data[chat_id]['state'] = 'waiting_for_food_usage'
        keyboard = [
            [InlineKeyboardButton("بله", callback_data='used_food')],
            [InlineKeyboardButton("خیر", callback_data='not_used_food')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await context.bot.send_message(chat_id=chat_id, text="آیا تاکنون از غذای دانشگاه استفاده کرده‌اید؟", reply_markup=reply_markup)

async def handle_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    chat_id = query.from_user.id
    callback_data = query.data

    if callback_data in ['used_food', 'not_used_food']:
        food_usage = 'Yes' if callback_data == 'used_food' else 'No'
        user_data[chat_id]['food_usage'] = food_usage
        save_to_excel(chat_id, user_data[chat_id])
        
        keyboard = [
            [InlineKeyboardButton(f"غذای روز (موجودی: {len(daily_food_codes)})", callback_data='daily_food')],
            [InlineKeyboardButton(f"غذای رایگان (موجودی: {len(free_food_codes)})", callback_data='free_food')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.edit_text("لطفاً یکی از گزینه‌های زیر را انتخاب کنید:", reply_markup=reply_markup)
    
    elif callback_data == 'daily_food':
        if len(daily_food_codes) > 0:
            await context.bot.send_message(chat_id=chat_id, text="لطفاً فیش واریزی خود را ارسال کنید:")
            user_data[chat_id]['state'] = 'awaiting_payment'
        else:
            await query.message.edit_text("کدهای غذای روز تمام شده‌اند.")
        await query.answer()

    elif callback_data == 'free_food':
        if len(free_food_codes) > 0:
            code = free_food_codes.pop(0)
            await query.message.edit_text(f"کد غذای رایگان شما: {code}")
            user_data[chat_id]['free_food_code'] = code
            save_to_excel(chat_id, user_data[chat_id])
        else:
            await query.message.edit_text("کدهای غذای رایگان تمام شده‌اند.")
        await query.answer()

async def handle_photo(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    state = user_data.get(chat_id, {}).get('state')

    if state == 'awaiting_payment':
        photo_file = update.message.photo[-1]
        student_id = user_data.get(chat_id, {}).get('student_id', 'نامشخص')
        
        # ارسال عکس به ادمین با دکمه‌های تایید و رد
        keyboard = [
            [InlineKeyboardButton("تایید", callback_data=f'approve_{chat_id}')],
            [InlineKeyboardButton("رد", callback_data=f'reject_{chat_id}')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # ارسال عکس به ادمین و ذخیره پیام
        message = await context.bot.send_photo(
            chat_id=admin_chat_id, 
            photo=photo_file.file_id, 
            caption=f"فیش واریزی از کاربر {chat_id} (شماره دانشجویی: {student_id}) دریافت شد.",
            reply_markup=reply_markup
        )
        pending_payment_messages[chat_id] = message.message_id
        
        # اطلاع‌رسانی به کاربر
        await context.bot.send_message(chat_id=chat_id, text="فیش واریزی شما دریافت شد. لطفاً منتظر تایید ادمین باشید.")
        user_data[chat_id]['state'] = 'waiting_for_confirmation'

async def confirm_payment(update: Update, context: CallbackContext):
    query = update.callback_query
    callback_data = query.data
    chat_id = int(callback_data.split('_')[1])  # دریافت chat_id از callback_data

    if 'approve' in callback_data:
        if user_data.get(chat_id) and user_data[chat_id]['state'] == 'waiting_for_confirmation':
            if len(daily_food_codes) > 0:
                code = daily_food_codes.pop(0)
                await context.bot.send_message(chat_id=chat_id, text=f"پرداخت شما تایید شد. کد غذای روز شما: {code}")
                user_data[chat_id]['payment_status'] = 'Approved'
            else:
                await context.bot.send_message(chat_id=chat_id, text="کدهای غذای روز تمام شده‌اند.")
                user_data[chat_id]['payment_status'] = 'Approved'
            await context.bot.send_message(chat_id=admin_chat_id, text=f"پرداخت کاربر {chat_id} تایید شد.")
            user_data[chat_id]['approval_status'] = 'Approved'
            user_data[chat_id]['state'] = 'completed'
        else:
            await context.bot.send_message(chat_id=admin_chat_id, text="کاربر یافت نشد یا در انتظار تایید نیست.")
    
    elif 'reject' in callback_data:
        await context.bot.send_message(chat_id=chat_id, text="پرداخت شما رد شد. لطفاً مجدداً فیش واریزی جدید ارسال کنید.")
        await context.bot.send_message(chat_id=admin_chat_id, text=f"پرداخت کاربر {chat_id} رد شد.")
        user_data[chat_id]['approval_status'] = 'Rejected'
        user_data[chat_id]['payment_status'] = 'Rejected'
        user_data[chat_id]['state'] = 'awaiting_payment'  # بازگشت به حالت انتظار برای پرداخت جدید
    
    # حذف پیام مربوط به فیش واریزی
    if chat_id in pending_payment_messages:
        await context.bot.delete_message(chat_id=admin_chat_id, message_id=pending_payment_messages[chat_id])
        del pending_payment_messages[chat_id]

    # ذخیره اطلاعات در فایل اکسل
    save_to_excel(chat_id, user_data[chat_id])

def save_to_excel(chat_id, data):
    try:
        workbook = openpyxl.load_workbook(EXCEL_FILE)
        sheet = workbook.active
        sheet.append([
            chat_id,
            data.get('student_id', ''),
            data.get('password', ''),
            data.get('food_usage', ''),
            data.get('approval_status', ''),
            data.get('payment_status', ''),
            data.get('free_food_code', '')
        ])
        workbook.save(EXCEL_FILE)
    except Exception as e:
        print(f"An error occurred: {e}")

async def main():
    application = Application.builder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(CallbackQueryHandler(handle_callback, pattern='^(used_food|not_used_food|daily_food|free_food)$'))
    application.add_handler(CallbackQueryHandler(confirm_payment, pattern='^(approve_|reject_)'))

    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main())
