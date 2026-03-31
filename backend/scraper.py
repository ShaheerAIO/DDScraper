"""
DoorDash store page scraper using Playwright.

Strategy (proven via testing):
1. Parse RSC (React Server Components) payload for rich item data:
   - Every item gets: id, name, description, displayPrice, imageUrl, ratings, badges
   - Categories with full item lists
2. Fallback to application/ld+json if RSC extraction fails.
3. Extract store name from ld+json Restaurant block.
"""

import html as html_mod
import json
import re
from playwright.async_api import async_playwright


def parse_store_url(url: str) -> str:
    """Extract the numeric store segment from a DoorDash URL."""
    match = re.search(r"/store/[^/]+/(\d+)", url)
    if match:
        return match.group(1)
    match = re.search(r"/store/([^/?]+)", url)
    if match:
        return match.group(1)
    raise ValueError(f"Could not parse store identifier from URL: {url}")


async def scrape_store(url: str) -> dict:
    """Load a DoorDash store page and extract menu data."""
    store_id = parse_store_url(url)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        page = await context.new_page()

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception:
            pass

        await page.wait_for_timeout(5000)

        # --- Strategy 1: Extract rich data from RSC payload ---
        item_lists = await _extract_rsc_item_lists(page)

        # --- Strategy 2: Fallback to ld+json ---
        ld_json_sections = None
        if not item_lists:
            ld_json_sections = await _extract_ld_json_menu(page)

        if not item_lists and not ld_json_sections:
            await browser.close()
            raise RuntimeError(
                "Could not find menu data on the DoorDash page. "
                "The store may be unavailable or the page structure may have changed."
            )

        # --- Extract store name from ld+json Restaurant ---
        store_name = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
                try {
                    const d = JSON.parse(s.textContent);
                    if (d['@type'] === 'Restaurant') {
                        return d.name || null;
                    }
                } catch(e) {}
            }
            return null;
        }""")

        await browser.close()

    if store_name:
        store_name = html_mod.unescape(store_name)

    if item_lists:
        return {
            "store_id": store_id,
            "store_name": store_name,
            "source": "rsc",
            "item_lists": item_lists,
        }
    else:
        return {
            "store_id": store_id,
            "store_name": store_name,
            "source": "ld_json",
            "sections": ld_json_sections,
        }


async def _extract_rsc_item_lists(page) -> list:
    """
    Extract itemLists from the RSC (React Server Components) Flight payload.
    Returns a list of category dicts, each with 'name' and 'items' (list of MenuPageItem).
    """
    try:
        payload = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script');
            for (const s of scripts) {
                const t = s.textContent || '';
                if (t.includes('MenuPageItemList') && t.includes('itemLists')) {
                    const match = t.match(/self\\.__next_f\\.push\\(\\[1,"(.*)"\\]\\)/s);
                    if (match) {
                        try { return JSON.parse('"' + match[1] + '"'); }
                        catch(e) { return null; }
                    }
                }
            }
            return null;
        }""")

        if not payload:
            return []

        # Find the "itemLists":[ array in the unescaped payload
        idx = payload.find('"itemLists":[')
        if idx < 0:
            return []

        arr_start = payload.find('[', idx)
        bracket = 0
        arr_end = arr_start
        for i in range(arr_start, len(payload)):
            if payload[i] == '[':
                bracket += 1
            elif payload[i] == ']':
                bracket -= 1
                if bracket == 0:
                    arr_end = i + 1
                    break

        raw = payload[arr_start:arr_end]
        # Replace RSC references ("$Lxx", "$xx") with null so JSON parses
        cleaned = re.sub(r'"\$L?[0-9a-f]+"', '"__ref__"', raw)
        return json.loads(cleaned)

    except Exception:
        return []


async def _extract_ld_json_menu(page) -> list:
    """Fallback: extract menu sections from ld+json."""
    try:
        menu_text = await page.evaluate("""() => {
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
                try {
                    const d = JSON.parse(s.textContent);
                    if (d['@type'] === 'Menu' || d.hasMenuSection) {
                        return s.textContent;
                    }
                } catch(e) {}
            }
            return null;
        }""")

        if not menu_text:
            return []

        menu = json.loads(menu_text)
        sections = menu.get("hasMenuSection", [])
        if sections and isinstance(sections[0], list):
            sections = sections[0]
        return sections

    except Exception:
        return []
