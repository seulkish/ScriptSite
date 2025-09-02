from playwright.sync_api import sync_playwright
from urllib.parse import urlsplit, urlunsplit
import csv
import re
from datetime import datetime 

# 현재 시각으로 버전 태그 생성
now = datetime.now()
version = now.strftime("%Y%m%d_%H%M")

START_URL = "https://apply.jinhakapply.com/"
OUTPUT_CSV = f"jinhak_ac_kr_links_{version}.csv"

def normalize_url_to_domain(url: str) -> str:
    """
    링크를 정규화하되, 경로/쿼리/프래그먼트 제거하지 않고 유지.
    """
    parts = urlsplit(url)
    # 스킴 보존 (http/https)
    scheme = parts.scheme or "http"
    if not parts.netloc:
        return url
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))

def clean_text(s: str) -> str:
    if not s:
        return ""
    # 공백/개행 정리 및 다중 공백 -> 단일 공백
    s = re.sub(r"\s+", " ", s.strip())
    return s

def extract_school_name(anchor) -> str:
    """
    가능한 경우 앵커 내부의 학교명 영역을 우선 사용.
    없으면 앵커 텍스트/타이틀/aria-label 순으로 추출.
    """
    try:
        # 예시: <a> 내부에 .univ_tit span 구조가 있을 수 있음
        name_el = anchor.query_selector(".univ_tit span") or anchor.query_selector(".univ_tit")
        if name_el:
            t = name_el.inner_text()
            t = clean_text(t)
            if t:
                return t
    except:
        pass

    # 앵커 자체 텍스트
    try:
        t = clean_text(anchor.inner_text())
        if t:
            # 너무 길거나 링크 텍스트가 URL이면 버림
            if not re.match(r"https?://", t, re.I):
                return t
    except:
        pass

    # title / aria-label 속성
    for attr in ["title", "aria-label"]:
        try:
            v = clean_text(anchor.get_attribute(attr))
            if v:
                return v
        except:
            pass

    return ""  # 최후의 수단: 빈 값 (나중에 도메인으로 대체)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            java_script_enabled=True,
        )
        page = context.new_page()
        page.goto(START_URL, wait_until="networkidle", timeout=60_000)

        # 혹시 '더보기' 같은 버튼이 있다면 자동 클릭 시도 (필요 없으면 무시됨)
        load_more_selectors = [
            "text=더보기", "text=전체보기", "button:has-text('더보기')", "a:has-text('더보기')"
        ]
        for sel in load_more_selectors:
            try:
                while True:
                    btn = page.query_selector(sel)
                    if not btn:
                        break
                    if not btn.is_visible():
                        break
                    btn.click()
                    page.wait_for_load_state("networkidle")
            except:
                pass

        anchors = page.query_selector_all("a[href]")
        results = {}
        for a in anchors:
            href = a.get_attribute("href")
            if not href:
                continue

            # 절대 URL만 대상으로 (상대경로 제외)
            if not href.lower().startswith("http"):
                continue
            # if ".ac.kr" not in href.lower(): // 필요시 변경 
            #     continue

            school_name = extract_school_name(a)
            school_name = re.sub(r'[\"“”]', '', school_name).strip()
            key = (school_name, href)
            # 중복 제거
            results[key] = None

        # # 정렬: 학교이름 기준
        # sorted_rows = sorted(results.keys(), key=lambda x: x[0])

        # # 콘솔 출력
        # for school, link in sorted_rows:
        #     print(f"{school} | {link}")

        # # CSV 저장
        # with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
        #     writer = csv.writer(f)
        #     writer.writerow(["학교이름", "링크"])
        #     for school, link in sorted_rows:
        #         school = school.replace('"', '')  # 따옴표 제거
        #         writer.writerow([school, link])

        # print(f"\n총 {len(sorted_rows)}개 추출됨 → {OUTPUT_CSV}")

        # 출력: 도메인 순서 기준
        for school, link in results.keys():
            school = school.replace('"', '')  # 따옴표 제거
            print(f"{school} | {link}")
        
        # CSV 저장
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["학교이름", "링크"])
            for school, link in results.keys():
                writer.writerow([school, link])

        print(f"\n총 {len(results.keys())}개 추출됨 → {OUTPUT_CSV}")

        context.close()
        browser.close()

if __name__ == "__main__":
    main()
