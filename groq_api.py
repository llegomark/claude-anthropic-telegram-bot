import os
from groq import Groq
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import time
import logging

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

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


# Adjust these values based on your Groq API limits
rate_limiter = RateLimiter(rpm_limit=30, tpm_limit=30000)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    retry=retry_if_exception_type((Exception,)),
    reraise=True
)
async def generate_response(messages: list, system_message: str) -> str:
    try:
        # Estimate token count (this is a rough estimate, you may want to use a proper tokenizer)
        estimated_tokens = sum(len(m['content'].split())
                               for m in messages) + len(system_message.split())

        rate_limiter.wait_if_needed(estimated_tokens)

        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_message},
                *messages
            ],
            max_tokens=1024,
            top_p=1,
            temperature=1,
            stop=None,
        )

        if response.choices and len(response.choices) > 0:
            return response.choices[0].message.content
        else:
            return "I apologize, but I couldn't formulate a response at this moment. Please try again."
    except Exception as e:
        logger.error(f"Error generating response: {str(e)}")
        raise
