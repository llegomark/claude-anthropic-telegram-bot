import os
import anthropic
from groq import Groq
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time
import logging

load_dotenv()

anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

logger = logging.getLogger(__name__)


class RateLimiter:
    def __init__(self, rpm_limit, tpm_limit):
        self.rpm_limit = rpm_limit
        self.tpm_limit = tpm_limit
        self.request_tokens = []
        self.token_tokens = []

    def wait_if_needed(self, tokens):
        current_time = time.time()

        self.request_tokens = [
            t for t in self.request_tokens if current_time - t < 60]
        self.token_tokens = [
            t for t in self.token_tokens if current_time - t < 60]

        if len(self.request_tokens) >= self.rpm_limit or sum(self.token_tokens) + tokens > self.tpm_limit:
            sleep_time = 60 - \
                (current_time - min(self.request_tokens + self.token_tokens))
            logger.info(f"Rate limit reached. Sleeping for {
                        sleep_time:.2f} seconds")
            time.sleep(sleep_time)

        self.request_tokens.append(current_time)
        self.token_tokens.append(tokens)


# Adjust these values based on your API limits
anthropic_rate_limiter = RateLimiter(rpm_limit=1000, tpm_limit=80000)
groq_rate_limiter = RateLimiter(rpm_limit=30, tpm_limit=30000)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type(
        (anthropic.APIConnectionError, anthropic.APITimeoutError, anthropic.RateLimitError)),
    reraise=True
)
async def generate_response_anthropic(messages: list, system_message: str) -> str:
    try:
        estimated_tokens = sum(len(m['content'].split())
                               for m in messages) + len(system_message.split())
        anthropic_rate_limiter.wait_if_needed(estimated_tokens)

        response = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20240620",
            max_tokens=4096,
            system=system_message,
            messages=messages
        )

        if response.content and len(response.content) > 0:
            return response.content[0].text
        else:
            return "I apologize, but I couldn't formulate a response at this moment. Please try again."
    except anthropic.RateLimitError as e:
        logger.error(f"Rate limit exceeded: {str(e)}")
        retry_after = int(e.response.headers.get('retry-after', 60))
        logger.info(f"Retrying after {retry_after} seconds")
        time.sleep(retry_after)
        raise
    except anthropic.APIStatusError as e:
        logger.error(f"API Status Error: {e.status_code} - {e.message}")
        if e.status_code in (500, 529):
            raise anthropic.APIError(f"Server error: {e.message}")
        else:
            raise
    except (anthropic.APIConnectionError, anthropic.APITimeoutError) as e:
        logger.error(f"Network error occurred: {str(e)}")
        raise
    except anthropic.APIError as e:
        logger.error(f"API error occurred: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Unexpected error occurred: {str(e)}")
        raise


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
async def generate_response_groq(messages: list, system_message: str) -> str:
    try:
        estimated_tokens = sum(len(m['content'].split())
                               for m in messages) + len(system_message.split())
        groq_rate_limiter.wait_if_needed(estimated_tokens)

        response = groq_client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_message},
                *messages
            ],
            max_tokens=1024,
            temperature=1,
            top_p=1,
            stop=None,
        )

        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            return "I apologize, but I couldn't formulate a response at this moment. Please try again."
    except Exception as e:
        logger.error(f"Error generating response with Groq: {str(e)}")
        raise


def get_generate_response(provider: str):
    if provider == "anthropic":
        return generate_response_anthropic
    elif provider == "groq":
        return generate_response_groq
    else:
        raise ValueError(f"Unknown provider: {provider}")
