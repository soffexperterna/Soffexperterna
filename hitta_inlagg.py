from playwright.sync_api import sync_playwright

URL = "https://www.facebook.com/difhockeyse"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(locale="sv-SE", viewport={"width":1280,"height":900})
    print("Öppnar Djurgården Hockey...")
    page.goto(URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(6000)

    print("Letar efter inlägg...")
    links = page.locator("a")
    hittade = set()

    for i in range(links.count()):
        try:
            href = links.nth(i).get_attribute("href")
            text = links.nth(i).inner_text().strip()

            if not href:
                continue

            if any(x in href for x in ["/posts/", "/photos/", "/videos/", "/reel/", "/permalink/", "fbid="]):
                if href.startswith("/"):
                    href = "https://www.facebook.com" + href
                if href not in hittade:
                    hittade.add(href)
                    print()
                    print("INLÄGG:", href)
                    if text:
                        print("TEXT:", text[:200].replace("\\n", " "))
        except Exception:
            pass

    print()
    print("=" * 50)
    print(f"Hittade {len(hittade)} möjliga inlägg.")
    browser.close()
