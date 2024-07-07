import re


def format_message(message: str) -> str:
    if not isinstance(message, str):
        # If message is not a string, convert it to a string
        message = str(message)

    # Replace '```' code blocks with '`' for inline code in Telegram
    message = re.sub(r'```(\w+)?\n(.*?)\n```',
                     r'`\2`', message, flags=re.DOTALL)

    # Replace '**' with '*' for bold text in Telegram
    message = re.sub(r'\*\*(.*?)\*\*', r'*\1*', message)

    # Replace '__' with '_' for italic text in Telegram
    message = re.sub(r'__(.*?)__', r'_\1_', message)

    return message
