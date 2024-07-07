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

    # Handle strikethrough text (~~text~~)
    message = re.sub(r'~~(.*?)~~', r'~\1~', message)

    # Handle underline text (__text__)
    message = re.sub(r'___(.+?)___', r'__\1__', message)

    # Handle spoiler text (||text||)
    message = re.sub(r'\|\|(.*?)\|\|', r'|||\1|||', message)

    # Handle inline URLs ([text](URL))
    message = re.sub(r'\[([^\]]+)\]\(([^\)]+)\)', r'[\1](\2)', message)

    # Handle user mentions (@username)
    message = re.sub(r'@(\w+)', r'@\1', message)

    # Handle hashtags (#hashtag)
    message = re.sub(r'#(\w+)', r'#\1', message)

    # Handle emoji (no change needed, Telegram supports emoji natively)

    # Escape special characters that are not part of Markdown syntax
    special_chars = ['\\', '`', '*', '_',
                     '{', '}', '[', ']', '(', ')', '#', '+', '-', '.', '!']
    for char in special_chars:
        message = message.replace(char, '\\' + char)

    return message


def truncate_message(message: str, max_length: int = 4096) -> str:
    """
    Truncate the message to fit Telegram's message length limit.

    Args:
    message (str): The message to truncate.
    max_length (int): The maximum allowed length of the message. Default is 4096.

    Returns:
    str: The truncated message.
    """
    if len(message) <= max_length:
        return message

    truncated = message[:max_length-3] + "..."
    return truncated


def split_long_message(message: str, max_length: int = 4096) -> list:
    """
    Split a long message into multiple parts that fit Telegram's message length limit.

    Args:
    message (str): The message to split.
    max_length (int): The maximum allowed length of each message part. Default is 4096.

    Returns:
    list: A list of message parts.
    """
    if len(message) <= max_length:
        return [message]

    parts = []
    while len(message) > max_length:
        part = message[:max_length]
        last_newline = part.rfind('\n')
        if last_newline != -1:
            part = message[:last_newline]
            message = message[last_newline+1:]
        else:
            message = message[max_length:]
        parts.append(part)

    if message:
        parts.append(message)

    return parts


def sanitize_input(input_text: str) -> str:
    """
    Sanitize user input to prevent potential security issues.

    Args:
    input_text (str): The input text to sanitize.

    Returns:
    str: The sanitized input text.
    """
    # Remove any HTML tags
    sanitized = re.sub(r'<[^>]+>', '', input_text)

    # Escape special characters
    sanitized = re.sub(r'([&<>"\'])', r'\\\1', sanitized)

    return sanitized
