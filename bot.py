import logging
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv
import os
from anthropic_api import generate_response
from utils import format_message
from auth import (
    is_authenticated, authenticate_user, save_user_history, load_user_history, AUTH_CODE, save_user_scenario, load_user_scenario,
    archive_user_history
)
from scenarios import SCENARIOS
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

load_dotenv()

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    filename='bot.log'
)
logger = logging.getLogger(__name__)

API_TIMEOUT = 30
TYPING_INTERVAL = 5


def escape_markdown(text):
    """Escape Markdown special characters."""
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(f'\\{char}' if char in escape_chars else char for char in text)

# Retry decorator for send_message


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((NetworkError, TimedOut)),
    reraise=True
)
async def send_message_with_retry(context, chat_id, text, reply_markup=None):
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=escape_markdown(text),
            parse_mode='MarkdownV2',
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        # If Markdown parsing fails, send without parsing
        await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )


async def send_typing_with_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message: str):
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(TYPING_INTERVAL)
    await send_message_with_retry(context, chat_id, message)

# Command handlers


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_authenticated(user_id):
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)

        commands = (
            "Available commands:\n"
            "/start - Start a new conversation\n"
            "/help - Show this help message\n"
            "/clear - Clear all your conversation histories\n"
            "/scenario - Change your current chat scenario"
        )

        message = (
            f"Welcome back! Your current scenario is {scenario}. "
            f"You can continue chatting with me now.\n\n{commands}"
        )

        await send_message_with_retry(context, update.effective_chat.id, message)
    else:
        await send_message_with_retry(context, update.effective_chat.id, "Greetings! To get started, please provide the secret code.")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, but I can only assist authenticated users. Please provide the secret code first.")
        return

    help_text = """
    Here are the available commands:
    /start - Start a new conversation
    /help - Show this help message
    /clear - Warning: This will clear all your conversation histories across all scenarios
    /scenario - Change your current chat scenario

    You can also send me any message, and I'll do my best to assist you based on the current scenario!
    """

    await send_message_with_retry(context, update.effective_chat.id, help_text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, but I can only assist authenticated users. Please provide the secret code first.")
        return

    # Archive all scenarios instead of clearing
    for scenario in SCENARIOS.keys():
        archive_user_history(user_id, scenario)

    # Clear the current context
    context.user_data['messages'] = []
    context.user_data['scenario'] = 'boyfriend'  # Reset to default scenario

    await send_message_with_retry(context, update.effective_chat.id, "All your conversation histories across all scenarios have been cleared.")


async def change_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, but I can only assist authenticated users. Please provide the secret code first.")
        return

    keyboard = [
        [InlineKeyboardButton("Demon Slayer", callback_data='demon_slayer'),
         InlineKeyboardButton("Boyfriend", callback_data='boyfriend')],
        [InlineKeyboardButton("Best Friend", callback_data='best_friend'),
         InlineKeyboardButton("Mentor", callback_data='mentor')],
        [InlineKeyboardButton("Sibling", callback_data='sibling'),
         InlineKeyboardButton("Coach", callback_data='coach')],
        [InlineKeyboardButton("Guidance Counselor", callback_data='guidance_counselor'),
         InlineKeyboardButton("Socratic Tutor", callback_data='socratic_tutor')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Choose a scenario to switch to:\n\n"
             "🗡️ Demon Slayer: Become a brave warrior in early 20th century Japan\n"
             "💑 Boyfriend: Experience life as a caring high school boyfriend\n"
             "🤝 Best Friend: Chat with a supportive and fun-loving best friend\n"
             "📚 Mentor: Interact with a wise and supportive high school teacher\n"
             "👶 Sibling: Talk with your 6-year-old younger brother\n"
             "🏋️ Coach: Get motivated by a dedicated high school sports coach\n"
             "🧠 Guidance Counselor: Seek advice from the school counselor\n"
             "🎓 Socratic Tutor: Learn through guided questioning\n\n"
             "Select an option to change your current scenario:",
        reply_markup=reply_markup
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    new_scenario = query.data
    old_scenario = context.user_data.get('scenario', 'boyfriend')
    context.user_data['scenario'] = new_scenario
    context.user_data['messages'] = load_user_history(user_id, new_scenario)
    save_user_scenario(user_id, new_scenario)

    scenario_descriptions = {
        'demon_slayer': "Demon Slayer - You're now a brave warrior in early 20th century Japan!",
        'boyfriend': "Boyfriend - You're now experiencing life as a caring high school boyfriend!",
        'best_friend': "Best Friend - You're now chatting with a supportive and fun-loving best friend!",
        'mentor': "Mentor - You're now interacting with a wise and supportive high school teacher!",
        'sibling': "Sibling - You're now talking with your 6-year-old younger brother!",
        'coach': "Coach - You're now being motivated by a dedicated high school sports coach!",
        'guidance_counselor': "Guidance Counselor - You're now seeking advice from the school counselor!",
        'socratic_tutor': "Socratic Tutor - You're now learning through guided questioning!"
    }

    await query.edit_message_text(
        text=f"Scenario changed from {old_scenario} to {
            scenario_descriptions[new_scenario]}\n\n"
        f"Your conversation history has been switched to the new scenario. Enjoy chatting!"
    )


async def send_typing_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    while True:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4.5)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = update.message.text
    chat_id = update.effective_chat.id

    logger.info(f"Received message from user {user_id}: {
                user_message[:20]}...")  # Log truncated message

    if not is_authenticated(user_id):
        if user_message == AUTH_CODE:
            authenticate_user(user_id)
            scenario = load_user_scenario(user_id)
            context.user_data['scenario'] = scenario
            context.user_data['messages'] = load_user_history(
                user_id, scenario)

            commands = (
                "Available commands:\n"
                "/start - Start a new conversation\n"
                "/help - Show this help message\n"
                "/clear - Clear your conversation history\n"
                "/scenario - Change the current chat scenario"
            )

            message = (
                f"You're now authenticated! Your current scenario is {
                    scenario}. "
                f"You can start chatting with me now.\n\n{commands}"
            )

            await send_message_with_retry(context, chat_id, message)
        else:
            await send_message_with_retry(context, chat_id, "I'm sorry, but I can only assist authenticated users. Please provide the secret code.")
        return

    if 'messages' not in context.user_data:
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)

    context.user_data['messages'].append(
        {"role": "user", "content": user_message})

    try:
        typing_task = asyncio.create_task(send_typing_action(context, chat_id))

        scenario = context.user_data['scenario']
        system_message = SCENARIOS[scenario]

        start_time = time.time()
        response = await asyncio.wait_for(generate_response(context.user_data['messages'], system_message), timeout=API_TIMEOUT)
        end_time = time.time()

        typing_task.cancel()

        response_time = end_time - start_time
        logger.info(f"API response time: {response_time:.2f} seconds")

        if response_time > 15:
            await send_typing_with_message(context, chat_id, "I'm thinking deeply about this. Please give me a moment...")

        formatted_response = format_message(response)

        context.user_data['messages'].append(
            {"role": "assistant", "content": response})
        save_user_history(user_id, context.user_data['messages'], scenario)

        await send_message_with_retry(context, chat_id, formatted_response)

        logger.info(f"Sent response to user {user_id}: {
                    formatted_response[:20]}...")  # Log truncated response

    except asyncio.TimeoutError:
        logger.error(f"API request timed out for user {user_id}")
        await send_message_with_retry(context, chat_id, "I'm sorry, but it's taking me longer than usual to respond. Please try again in a moment.")
    except Exception as e:
        logger.error(f"Error handling message for user {
                     user_id}: {str(e)}", exc_info=True)
        error_message = "I apologize, but I've encountered an error while processing your request. "
        if isinstance(e, NetworkError):
            error_message += "There was a network error. Please check your connection and try again."
        elif isinstance(e, TimedOut):
            error_message += "The request timed out. Please try again in a moment."
        else:
            error_message += "Please try again later."
        await send_message_with_retry(context, chat_id, error_message)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    error_message = "Sorry, something went wrong. Please try again later."
    if isinstance(context.error, NetworkError):
        error_message = "Network error occurred. Please check your connection."
    elif isinstance(context.error, TimedOut):
        error_message = "Request timed out. Please try again."

    if update and update.effective_chat:
        await send_message_with_retry(context, update.effective_chat.id, error_message)


def main():
    application = Application.builder().token(
        os.getenv("TELEGRAM_BOT_TOKEN")).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(CommandHandler("scenario", change_scenario))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))

    application.add_error_handler(error_handler)

    application.run_polling(poll_interval=1.0, timeout=30)


if __name__ == '__main__':
    main()
