"""
Maps scraped DoorDash data into the 14-sheet Excel model.

Supports two data sources:
  - RSC (React Server Components): richer data with imageUrl for every item
  - ld+json (schema.org): fallback with basic name/description/price
"""

from __future__ import annotations

import html
from typing import Optional


def map_to_model(raw: dict) -> dict:
    source = raw.get("source", "ld_json")
    if source == "rsc":
        return _map_rsc(raw)
    else:
        return _map_ld_json(raw)


def _map_rsc(raw: dict) -> dict:
    """Map RSC-sourced data (MenuPageItem objects) into the Excel model."""
    store_id = raw.get("store_id", "unknown")
    store_name = raw.get("store_name") or "DoorDash Import"
    item_lists = raw.get("item_lists", [])

    menu_id = 1
    cat_counter = 0
    item_counter = 0
    cat_item_counter = 0

    menus = []
    categories = []
    items = []
    category_items = []

    seen_items = {}  # item dd_id -> our_id

    menus.append({
        "id": menu_id,
        "menuName": store_name,
        "posDisplayName": store_name,
        "posButtonColor": "#FCA98F",
        "picture": None,
        "sortOrder": 1,
    })

    for cat_idx, item_list in enumerate(item_lists):
        if not isinstance(item_list, dict):
            continue

        cat_counter += 1
        cat_id = cat_counter
        cat_name = _unescape(item_list.get("name", f"Category {cat_id}"))

        categories.append({
            "id": cat_id,
            "categoryName": cat_name,
            "posDisplayName": cat_name,
            "kdsDisplayName": cat_name,
            "color": "#FF7B42",
            "image": None,
            "kioskImage": None,
            "parentCategoryId": None,
            "tagIds": None,
            "menuIds": str(menu_id),
            "sortOrder": cat_idx + 1,
        })

        list_items = item_list.get("items", [])

        for item_idx, item_raw in enumerate(list_items):
            if not isinstance(item_raw, dict):
                continue

            dd_id = item_raw.get("id", "")
            item_name = _unescape(item_raw.get("name", "")).strip()
            if not item_name:
                continue

            # Dedup by DoorDash item ID
            dedup_key = dd_id if dd_id else item_name
            if dedup_key in seen_items:
                existing_id = seen_items[dedup_key]
                cat_item_counter += 1
                category_items.append({
                    "id": cat_item_counter,
                    "categoryId": cat_id,
                    "itemId": existing_id,
                    "sortOrder": item_idx + 1,
                })
                continue

            item_counter += 1
            item_id = item_counter
            seen_items[dedup_key] = item_id

            description = _unescape(item_raw.get("description", "") or "")
            price = _parse_dd_price(item_raw.get("displayPrice", ""))
            image = item_raw.get("imageUrl") or None

            items.append({
                "id": item_id,
                "itemName": item_name,
                "posDisplayName": item_name,
                "kdsName": item_name,
                "itemDescription": description,
                "itemPicture": image,
                "onlineImage": image,
                "landscapeImage": image,
                "thirdPartyImage": image,
                "kioskItemImage": image,
                "itemPrice": price,
                "taxLinkedWithParentSetting": True,
                "calculatePricesWithTaxIncluded": False,
                "takeoutException": False,
                "stockStatus": "inStock",
                "stockValue": 0,
                "orderQuantityLimit": True,
                "minLimit": 1,
                "maxLimit": 999,
                "noMaxLimit": False,
                "stationIds": "1",
                "preparationTime": None,
                "calories": None,
                "tagIds": None,
                "inheritTagsFromCategory": False,
                "saleCategory": "Food Sales",
                "allergenIds": None,
                "inheritModifiersFromCategory": False,
                "addonIds": None,
                "isSpecialRequest": True,
            })

            cat_item_counter += 1
            category_items.append({
                "id": cat_item_counter,
                "categoryId": cat_id,
                "itemId": item_id,
                "sortOrder": item_idx + 1,
            })

    return _build_result(store_id, menus, categories, items, category_items)


def _map_ld_json(raw: dict) -> dict:
    """Map ld+json (schema.org) data into the Excel model."""
    store_id = raw.get("store_id", "unknown")
    store_name = raw.get("store_name") or "DoorDash Import"
    sections = raw.get("sections", [])

    menu_id = 1
    cat_counter = 0
    item_counter = 0
    cat_item_counter = 0

    menus = []
    categories = []
    items = []
    category_items = []

    seen_items = {}

    menus.append({
        "id": menu_id,
        "menuName": store_name,
        "posDisplayName": store_name,
        "posButtonColor": "#FCA98F",
        "picture": None,
        "sortOrder": 1,
    })

    for cat_idx, section in enumerate(sections):
        cat_counter += 1
        cat_id = cat_counter
        cat_name = _unescape(section.get("name", f"Category {cat_id}"))

        categories.append({
            "id": cat_id,
            "categoryName": cat_name,
            "posDisplayName": cat_name,
            "kdsDisplayName": cat_name,
            "color": "#FF7B42",
            "image": None,
            "kioskImage": None,
            "parentCategoryId": None,
            "tagIds": None,
            "menuIds": str(menu_id),
            "sortOrder": cat_idx + 1,
        })

        menu_items = section.get("hasMenuItem", [])

        for item_idx, menu_item in enumerate(menu_items):
            item_name = _unescape(menu_item.get("name", "")).strip()
            if not item_name:
                continue

            if item_name in seen_items:
                existing_id = seen_items[item_name]
                cat_item_counter += 1
                category_items.append({
                    "id": cat_item_counter,
                    "categoryId": cat_id,
                    "itemId": existing_id,
                    "sortOrder": item_idx + 1,
                })
                continue

            item_counter += 1
            item_id = item_counter
            seen_items[item_name] = item_id

            description = _unescape(menu_item.get("description", "") or "")
            price = _parse_schema_price(menu_item)

            items.append({
                "id": item_id,
                "itemName": item_name,
                "posDisplayName": item_name,
                "kdsName": item_name,
                "itemDescription": description,
                "itemPicture": None,
                "onlineImage": None,
                "landscapeImage": None,
                "thirdPartyImage": None,
                "kioskItemImage": None,
                "itemPrice": price,
                "taxLinkedWithParentSetting": True,
                "calculatePricesWithTaxIncluded": False,
                "takeoutException": False,
                "stockStatus": "inStock",
                "stockValue": 0,
                "orderQuantityLimit": True,
                "minLimit": 1,
                "maxLimit": 999,
                "noMaxLimit": False,
                "stationIds": "1",
                "preparationTime": None,
                "calories": None,
                "tagIds": None,
                "inheritTagsFromCategory": False,
                "saleCategory": "Food Sales",
                "allergenIds": None,
                "inheritModifiersFromCategory": False,
                "addonIds": None,
                "isSpecialRequest": True,
            })

            cat_item_counter += 1
            category_items.append({
                "id": cat_item_counter,
                "categoryId": cat_id,
                "itemId": item_id,
                "sortOrder": item_idx + 1,
            })

    return _build_result(store_id, menus, categories, items, category_items)


def _build_result(store_id, menus, categories, items, category_items) -> dict:
    return {
        "store_id": store_id,
        "Menu": menus,
        "Category": categories,
        "Item": items,
        "Item Modifiers": [],
        "Category ModifierGroups": [],
        "Category Modifiers": [],
        "Category Items": category_items,
        "Item Modifier Group": [],
        "Modifier Group": [],
        "Modifier": [],
        "Modifier Option": [],
        "Modifier ModifierOptions": [],
        "Allergen": [],
        "Tag": [],
    }


# --- Helpers ---


def _unescape(text: str) -> str:
    if not text:
        return ""
    return html.unescape(text)


def _parse_dd_price(display_price: str) -> float:
    """Parse DoorDash displayPrice like '$$15.68' or '$9.99'."""
    if not display_price:
        return 0
    cleaned = display_price.replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0


def _parse_schema_price(menu_item: dict) -> float:
    """Extract price from schema.org MenuItem offers."""
    offers = menu_item.get("offers", {})
    raw = offers.get("price", 0) if isinstance(offers, dict) else 0
    if isinstance(raw, str):
        return _parse_dd_price(raw)
    return float(raw) if raw else 0
