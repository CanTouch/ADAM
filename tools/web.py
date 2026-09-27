"""Web search through DuckDuckGo (no API key)."""
from ddgs import DDGS

MAX_RESULTS = 5


def web_search(query):
    results = DDGS().text(query, max_results=MAX_RESULTS)
    if not results:
        return f"No results for '{query}'."
    return "\n\n".join(
        f"{i}. {r.get('title', '')}\n{r.get('href', '')}\n{r.get('body', '')}"
        for i, r in enumerate(results, 1)
    )
