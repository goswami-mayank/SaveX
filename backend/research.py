"""Bounded Exa recipe research; returned web content is untrusted data."""

import os
from urllib.parse import urlparse
import httpx


class ResearchError(Exception):
    pass


def search_recipes(ingredients: list[str], client=None):
    key = os.getenv("EXA_API_KEY")
    if not key:
        raise ResearchError("Exa API key is not configured")
    if not ingredients:
        return []
    query = "simple recipes using " + ", ".join(ingredients[:8])
    try:
        response = (client or httpx).post(
            "https://api.exa.ai/search",
            headers={"x-api-key": key},
            json={
                "query": query,
                "type": "auto",
                "numResults": 5,
                "contents": {"highlights": True},
            },
            timeout=15,
        )
        response.raise_for_status()
        results = response.json()["results"]
        if not isinstance(results, list):
            raise ValueError("invalid results")
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise ResearchError(
            "Recipe research is unavailable; retry or plan without web research"
        ) from exc
    sources = []
    for row in results:
        if not isinstance(row, dict):
            continue
        url = row.get("url", "")
        if not isinstance(url, str) or urlparse(url).scheme not in {"http", "https"}:
            continue
        highlights = row.get("highlights") or []
        sources.append(
            {
                "title": str(row.get("title") or "Recipe")[:200],
                "url": url,
                "highlights": [x[:500] for x in highlights[:2] if isinstance(x, str)],
            }
        )
    return sources


def _safe_https_url(value):
    """Keep externally sourced links suitable for direct browser display."""
    from ipaddress import ip_address
    from urllib.parse import urlsplit

    if not isinstance(value, str) or len(value) > 2048:
        return False
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or '').rstrip('.').lower()
        if parsed.scheme != 'https' or not host or parsed.username or parsed.password:
            return False
        if host == 'localhost' or host.endswith(('.localhost', '.local', '.internal')):
            return False
        try:
            return ip_address(host).is_global
        except ValueError:
            return '.' in host
    except ValueError:
        return False


def search_recipe_image(dish: str, client=None):
    """Find a related recipe photo and its page; do not fetch image URLs server-side."""
    import re
    key = os.getenv('EXA_API_KEY')
    if not key:
        raise ResearchError('Exa API key is not configured')
    try:
        response = (client or httpx).post(
            'https://api.exa.ai/search', headers={'x-api-key': key},
            json={'query': f'{dish[:200]} recipe food photograph', 'type': 'auto', 'numResults': 5, 'moderation': True, 'contents': {'extras': {'imageLinks': 2, 'richImageLinks': 2}}},
            timeout=12,
        )
        response.raise_for_status()
        results = response.json()['results']
        if not isinstance(results, list):
            raise ValueError('invalid results')
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        raise ResearchError('Recipe images are temporarily unavailable') from exc
    for row in results:
        if not isinstance(row, dict):
            continue
        source = row.get('url')
        if not _safe_https_url(source):
            continue
        extras = row.get('extras') if isinstance(row.get('extras'), dict) else {}
        rich = extras.get('richImageLinks') if isinstance(extras.get('richImageLinks'), list) else []
        links = extras.get('imageLinks') if isinstance(extras.get('imageLinks'), list) else []
        candidates = [row.get('image'), *(item.get('url') for item in rich if isinstance(item, dict)), *links]
        for image in candidates:
            if not _safe_https_url(image):
                continue
            if re.search(r'(?:^|[-_/])(logo|icon|favicon|avatar|sprite)(?:[-_.?/]|$)', image, re.I):
                continue
            return {'url': image, 'source_url': source, 'source_title': str(row.get('title') or 'Recipe source')[:200]}
    return None


def search_meal_images(meals: dict):
    """Search independently so a missing or failed image never discards a meal plan."""
    from concurrent.futures import ThreadPoolExecutor
    keys = ('breakfast', 'lunch', 'dinner')
    def lookup(key):
        try:
            return search_recipe_image(meals[key]['dish'])
        except Exception as exc:
            import logging
            logging.getLogger("savex").warning("Recipe image lookup failed: %s", type(exc).__name__)
            return None
    with ThreadPoolExecutor(max_workers=3) as executor:
        return dict(zip(keys, executor.map(lookup, keys)))
