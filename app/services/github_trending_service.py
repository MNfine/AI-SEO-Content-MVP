import requests
from typing import List, Dict

def get_github_trending_repos(period: str = "daily", language: str = "", limit: int = 10) -> List[Dict]:
    """
    Lấy danh sách repo trending từ github.com/trending (không cần API key, scrape HTML).
    period: daily, weekly, monthly
    language: lọc theo ngôn ngữ (nếu có)
    Trả về list dict: name, url, description, stars, stars_in_period
    """
    from bs4 import BeautifulSoup
    import re
    base_url = "https://github.com/trending"
    url = base_url
    if language:
        url += f"/{language}"
    url += f"?since={period}"
    headers = {"User-Agent": "Mozilla/5.0"}
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    repos = []
    for repo in soup.select("article.Box-row"):
        # Repo name
        a = repo.select_one("h2 a")
        if not a:
            continue
        name = a.get("href", "/").strip("/")
        url_full = f"https://github.com/{name}"
        # Description
        desc = repo.select_one("p")
        description = desc.text.strip() if desc else ""
        # Stars
        star_tag = repo.select_one(".Link--muted.d-inline-block.mr-3")
        stars = star_tag.text.strip().replace(",", "") if star_tag else "0"
        try:
            stars = int(stars)
        except Exception:
            stars = 0
        # Stars in period
        stars_period_tag = repo.select_one(".float-sm-right")
        stars_in_period = 0
        if stars_period_tag:
            m = re.search(r"\d+", stars_period_tag.text.replace(",", ""))
            if m:
                stars_in_period = int(m.group(0))
        repos.append({
            "name": name,
            "url": url_full,
            "description": description,
            "stars": stars,
            "stars_in_period": stars_in_period,
        })
        if len(repos) >= limit:
            break
    return repos