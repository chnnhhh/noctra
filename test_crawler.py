#!/usr/bin/env python3
"""Manual test script for JavDB crawler.

Usage:
    python test_crawler.py              # Test with default code
    python test_crawler.py SSIS-743     # Test with a specific code
"""

import asyncio
import sys

from app.scrapers.javdb import JavDBCrawler


async def main(code: str):
    """Run a manual crawl test for the given code."""
    print(f"=== JavDB Crawler Manual Test ===")
    print(f"Code: {code}")
    print()

    crawler = JavDBCrawler()

    try:
        print("Fetching metadata...")
        result = await crawler.crawl(code)

        if result is None:
            print(f"ERROR: No metadata found for code '{code}'")
            print("Possible reasons:")
            print("  - The code does not exist on JavDB")
            print("  - Network error or request blocked")
            print("  - Cloudflare challenge")
            return 1

        print("SUCCESS! Metadata found:")
        print(f"  Code:       {result.code}")
        print(f"  Title:      {result.title}")
        print(f"  Plot:       {result.plot[:100]}..." if len(result.plot) > 100 else f"  Plot:       {result.plot}")
        print(f"  Actors:     {', '.join(result.actors) if result.actors else '(none)'}")
        print(f"  Studio:     {result.studio or '(none)'}")
        print(f"  Release:    {result.release or '(none)'}")
        print(f"  Poster URL: {result.poster_url or '(none)'}")
        print()
        print("Full metadata dict:")
        print(result.to_dict())
        return 0

    except Exception as e:
        print(f"EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    code = sys.argv[1] if len(sys.argv) > 1 else "SSIS-743"
    exit_code = asyncio.run(main(code))
    sys.exit(exit_code)
