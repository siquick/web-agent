from exa_py import Exa
from dotenv import load_dotenv

import os

# Use .env to store your API key or paste it directly into the code
load_dotenv()
exa = Exa(os.getenv("EXA_API_KEY"))


def web_search(query: str, num_results: int = 3) -> list[str]:
    try:
        response = exa.search_and_contents(
            query, text=True, type="auto", num_results=num_results
        )
        return response
    except Exception:
        raise


def refine_web_search_into_context(results: list) -> str:
    context = ""
    counter = 0
    for result in results.results:
        counter += 1
        context += f"<result {result.url} id={counter}> {result.text}</result>\n"
    return context
