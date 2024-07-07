import logging
import asyncio
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler
from telegram.constants import ChatAction
from telegram.error import NetworkError, TimedOut
from dotenv import load_dotenv
import os
from ai_providers import get_generate_response
from utils import format_message, truncate_message, split_long_message, sanitize_input
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


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((NetworkError, TimedOut)),
    reraise=True
)
async def send_message_with_retry(context, chat_id, text, reply_markup=None):
    try:
        formatted_text = format_message(text)
        if len(formatted_text) > 4096:
            parts = split_long_message(formatted_text)
            for part in parts:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=part,
                    parse_mode='MarkdownV2',
                    reply_markup=reply_markup
                )
        else:
            await context.bot.send_message(
                chat_id=chat_id,
                text=formatted_text,
                parse_mode='MarkdownV2',
                reply_markup=reply_markup
            )
    except Exception as e:
        logger.error(f"Error sending message: {str(e)}")
        truncated_text = truncate_message(text)
        await context.bot.send_message(
            chat_id=chat_id,
            text=truncated_text,
            reply_markup=reply_markup
        )


async def send_typing_with_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message: str):
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
    await asyncio.sleep(TYPING_INTERVAL)
    await send_message_with_retry(context, chat_id, message)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if is_authenticated(user_id):
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)
        context.user_data['ai_provider'] = context.user_data.get(
            'ai_provider', 'groq')

        commands = (
            "🌟 Available commands:\n"
            "/start - Begin a fresh conversation\n"
            "/help - Learn more about Evander\n"
            "/clear - Reset your conversation history (use with caution!)\n"
            "/scenario - Change who you're talking to\n"
            "/provider - Switch between AI providers (Anthropic or Groq)"
        )

        message = (
            f"Welcome back, Argi! 🎭\n\n"
            f"You're currently chatting with your '{scenario}' using the {
                context.user_data['ai_provider'].capitalize()} AI provider. Ready for some engaging conversation?\n\n"
            f"Remember, you can change who you're talking to anytime with /scenario and switch AI providers with /provider.\n\n"
            f"{commands}\n\n"
            f"Now, what would you like to chat about with your {scenario}? 😃"
        )

        await send_message_with_retry(context, update.effective_chat.id, message)
    else:
        await send_message_with_retry(context, update.effective_chat.id, "Greetings, Argi! 🌟 To start chatting with Evander please provide the secret code. What's the password?")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, Argi, but I can only assist authenticated users. Please provide the secret code first.")
        return

    help_text = """
    Here are the available commands:
    /start - Begin a fresh conversation
    /help - Show this help message
    /clear - Warning: This will reset all your conversation histories across all scenarios
    /scenario - Change who you're talking to
    /provider - Switch between AI providers (Anthropic or Groq)

    You can also send me any message, and I'll respond based on the current scenario and selected AI provider!
    """

    await send_message_with_retry(context, update.effective_chat.id, help_text)


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, Argi, but I can only assist authenticated users. Please provide the secret code first.")
        return

    for scenario in SCENARIOS.keys():
        archive_user_history(user_id, scenario)

    context.user_data['messages'] = []
    context.user_data['scenario'] = 'boyfriend'
    context.user_data['ai_provider'] = 'groq'

    await send_message_with_retry(context, update.effective_chat.id, "All your conversation histories across all scenarios have been reset. The AI provider has been set to Anthropic (default).")


async def change_scenario(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, Argi, but I can only assist authenticated users. Please provide the secret code first.")
        return

    keyboard = [
        [InlineKeyboardButton("Demon Slayer", callback_data='demon_slayer'),
         InlineKeyboardButton("Boyfriend", callback_data='boyfriend')],
        [InlineKeyboardButton("Best Friend", callback_data='best_friend'),
         InlineKeyboardButton("Mentor", callback_data='mentor')],
        [InlineKeyboardButton("Sibling", callback_data='sibling'),
         InlineKeyboardButton("Coach", callback_data='coach')],
        [InlineKeyboardButton("Guidance Counselor", callback_data='guidance_counselor'),
         InlineKeyboardButton("Socratic Tutor", callback_data='socratic_tutor')],
        [InlineKeyboardButton("Mental Health Advocate",
                              callback_data='mental_health_advocate')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Choose who you'd like to talk to:\n\n"
             "🗡️ Demon Slayer: Chat with a brave warrior from Taisho-era Japan\n"
             "💑 Boyfriend: Talk to your caring high school boyfriend\n"
             "🤝 Best Friend: Hang out with your supportive and fun-loving best friend, Tiffany\n"
             "📚 Mentor: Seek wisdom from your high school teacher\n"
             "👶 Sibling: Play with your 6-year-old younger brother\n"
             "🏋️ Coach: Get motivated by your dedicated high school sports coach\n"
             "🧠 Guidance Counselor: Discuss your concerns with the school counselor\n"
             "🎓 Socratic Tutor: Learn through guided questioning\n\n"
             "💚 Mental Health Advocate: Talk to a compassionate mental health professional\n\n"
             "Select an option to change who you're talking to:",
        reply_markup=reply_markup
    )


async def change_provider(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_authenticated(user_id):
        await send_message_with_retry(context, update.effective_chat.id, "I'm sorry, Argi, but I can only assist authenticated users. Please provide the secret code first.")
        return

    keyboard = [
        [InlineKeyboardButton("Groq (LLaMA)", callback_data='groq'),
         InlineKeyboardButton("Anthropic (Claude)", callback_data='anthropic')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Choose your AI provider:\n\n"
             "🚀 Groq (LLaMA): Known for its fast inference and broad knowledge base\n"
             "🧠 Anthropic (Claude): Known for its strong reasoning and instruction-following capabilities\n\n"
             "Select an option to change your AI provider:",
        reply_markup=reply_markup
    )


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_user.id
    data = query.data

    if data in ['anthropic', 'groq']:
        old_provider = context.user_data.get('ai_provider', 'anthropic')
        context.user_data['ai_provider'] = data
        await query.edit_message_text(
            text=f"You've switched from {old_provider.capitalize()} to {
                data.capitalize()} as your AI provider.\n\n"
            f"Your conversation will now use the {
                data.capitalize()} model. Enjoy chatting!"
        )
    else:
        new_scenario = data
        old_scenario = context.user_data.get('scenario', 'boyfriend')
        context.user_data['scenario'] = new_scenario
        context.user_data['messages'] = load_user_history(
            user_id, new_scenario)
        save_user_scenario(user_id, new_scenario)

        scenario_descriptions = {
            'demon_slayer': "Demon Slayer - You're now chatting with a brave warrior from early 20th century Japan!",
            'boyfriend': "Boyfriend - You're now talking to your caring high school boyfriend!",
            'best_friend': "Best Friend - You're now hanging out with your supportive and fun-loving best friend, Tiffany!",
            'mentor': "Mentor - You're now seeking wisdom from your high school teacher!",
            'sibling': "Sibling - You're now playing with your 6-year-old younger brother!",
            'coach': "Coach - You're now getting motivated by your dedicated high school sports coach!",
            'guidance_counselor': "Guidance Counselor - You're now discussing your concerns with the school counselor!",
            'socratic_tutor': "Socratic Tutor - You're now learning through guided questioning!",
            'mental_health_advocate': "Mental Health Advocate - You're now talking to a compassionate mental health professional!"
        }

        await query.edit_message_text(
            text=f"You've switched from talking to your {
                old_scenario} to your {scenario_descriptions[new_scenario]}\n\n"
            f"Your conversation history has been updated to match. Enjoy chatting!"
        )


async def send_typing_action(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    while True:
        await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
        await asyncio.sleep(4.5)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_message = sanitize_input(update.message.text)
    chat_id = update.effective_chat.id

    logger.info(f"Received message from user {
                user_id}: {user_message[:20]}...")

    if not is_authenticated(user_id):
        if user_message == AUTH_CODE:
            authenticate_user(user_id)
            scenario = load_user_scenario(user_id)
            context.user_data['scenario'] = scenario
            context.user_data['messages'] = load_user_history(
                user_id, scenario)
            # Default to Groq
            context.user_data['ai_provider'] = 'groq'

            commands = (
                "Available commands:\n"
                "/start - Begin a fresh conversation\n"
                "/help - Learn more about Evander\n"
                "/clear - Reset your conversation history\n"
                "/scenario - Change who you're talking to\n"
                "/provider - Switch between AI providers (Anthropic or Groq)"
            )

            message = (
                f"You're now authenticated, Argi! Your current scenario is {
                    scenario} "
                f"and you're using the Anthropic AI provider. "
                f"You can start chatting now.\n\n{commands}"
            )

            await send_message_with_retry(context, chat_id, message)
        else:
            await send_message_with_retry(context, chat_id, "I'm sorry, Argi, but I can only assist authenticated users. Please provide the secret code.")
        return

    if 'messages' not in context.user_data:
        scenario = load_user_scenario(user_id)
        context.user_data['scenario'] = scenario
        context.user_data['messages'] = load_user_history(user_id, scenario)
        context.user_data['ai_provider'] = context.user_data.get(
            'ai_provider', 'groq')

    context.user_data['messages'].append(
        {"role": "user", "content": user_message})

    try:
        typing_task = asyncio.create_task(send_typing_action(context, chat_id))

        scenario = context.user_data['scenario']
        system_message = SCENARIOS[scenario]

        ai_provider = context.user_data.get('ai_provider', 'anthropic')
        generate_response = get_generate_response(ai_provider)

        start_time = time.time()
        response = await generate_response(context.user_data['messages'], system_message)
        end_time = time.time()

        typing_task.cancel()

        response_time = end_time - start_time
        logger.info(f"API response time: {response_time:.2f} seconds")

        if response_time > 15:
            await send_typing_with_message(context, chat_id, "I'm thinking deeply about this. Please give me a moment...")

        context.user_data['messages'].append(
            {"role": "assistant", "content": response})

        asyncio.create_task(save_user_history(
            user_id, context.user_data['messages'], scenario))

        await send_message_with_retry(context, chat_id, response)

        logger.info(f"Sent response to user {user_id}: {response[:20]}...")

    except Exception as e:
        logger.error(f"Error handling message for user {
                     user_id}: {str(e)}", exc_info=True)
        error_message = "I apologize, Argi, but I've encountered an error while processing your request. Please try again later."
        await send_message_with_retry(context, chat_id, error_message)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Exception while handling an update:", exc_info=context.error)
    error_message = "Sorry, Argi, something went wrong. Please try again later."
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
    application.add_handler(CommandHandler("provider", change_provider))
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CallbackQueryHandler(button))

    application.add_error_handler(error_handler)

    application.run_polling(poll_interval=1.0, timeout=30)


if __name__ == '__main__':
    main()
