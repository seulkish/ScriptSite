"""
사이트: https://apply.jinhakapply.com/
요구사항: 페이지에 노출된 대학교(링크)들을 하나씩 방문해보고, 문제 있는 학교 이름을 저장
방법: Playwright(헤드리스 브라우저)로 메인 페이지에서 대학 링크 수집 → 각 링크 접속/상태 체크 → 결과 CSV 저장

사용 전 준비:
  1) Python 3.9+
  2) pip install playwright
  3) playwright install

실행:
  python check_univ_links.py

출력:
  - results_all.csv : 모든 학교/링크/상태/비고
  - results_problem.csv : 문제 있다고 판단된 항목만

문제 판정 기준(초기값):
  - 응답이 없거나(goto 응답 None), status >= 400
  - 타임아웃/네비게이션 에러/SSL 에러 등 예외 발생
  - 제목(title)이 비정상(빈 문자열)인 경우
필요에 따라 is_problem 함수에서 조건을 조정하세요.
"""

import asyncio
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict
import csv
import re
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError

START_URL = "https://apply.jinhakapply.com/"
OUTPUT_ALL = Path("results_all.csv")
OUTPUT_PROBLEM = Path("results_problem.csv")

# 병렬 처리 제한 (과도한 동시 접속 방지)
MAX_CONCURRENCY = 8
# 각 페이지 이동 타임아웃(ms)
GOTO_TIMEOUT_MS = 20_000

@dataclass
class UnivLink:
    name: str
    href: str

@dataclass
class CheckResult:
    name: str
    href: str
    status: Optional[int]
    title: str
    ok: bool
    note: str

UNIV_LINK_SELECTOR = "ul.univ_list a[href]"  # 진학어플라이 대학 리스트(예시 HTML 기준)
UNIV_NAME_IN_A_SELECTOR = ".univ_tit span"

async def extract_univ_links(page) -> List[UnivLink]:
    # 페이지 내 모든 대학 링크 수집 (중복/빈 링크 제외)
    anchors = await page.query_selector_all(UNIV_LINK_SELECTOR)
    found: Dict[str, UnivLink] = {}
    for a in anchors:
        href = (await a.get_attribute("href")) or ""
        href = href.strip()
        if not href:
            continue
        # 절대/상대 경로 모두 허용. 상대경로는 메인 도메인 기준으로 변환
        if href.startswith("/"):
            href = START_URL.rstrip("/") + href

        # 끝에 .kr 까지만 남기도록 정리
        m = re.search(r"^(https?://[^/]*?\.kr)", href)
        if m:
            href = m.group(1)

        # 이름 추출
        name_node = await a.query_selector(UNIV_NAME_IN_A_SELECTOR)
        if name_node:
            name = (await name_node.inner_text()).strip()
        else:
            # 대안: 앵커 내 텍스트 통째로
            name = (await a.inner_text()).strip()
            name = re.sub(r"\s+", " ", name)
        if href not in found:
            found[href] = UnivLink(name=name or href, href=href)
    return list(found.values())

async def visit_and_check(context, item: UnivLink) -> CheckResult:
    status: Optional[int] = None
    title = ""
    note = ""
    ok = False
    page = await context.new_page()
    try:
        resp = await page.goto(item.href, wait_until="domcontentloaded", timeout=GOTO_TIMEOUT_MS)
        if resp:
            status = resp.status
        # 제목 시도
        try:
            title = (await page.title()) or ""
        except Exception:
            title = ""
        ok = not is_problem(status, title)
        if not ok:
            note = reason_text(status, title)
    except PWTimeoutError:
        note = "timeout"
    except Exception as e:
        note = f"exception: {type(e).__name__}: {e}"
    finally:
        await page.close()
    return CheckResult(name=item.name, href=item.href, status=status, title=title, ok=ok, note=note)

def is_problem(status: Optional[int], title: str) -> bool:
    if status is None:
        return True
    if status >= 400:
        return True
    # 제목이 너무 비정상이면(완전 빈 값)
    if title.strip() == "":
        return True
    return False

def reason_text(status: Optional[int], title: str) -> str:
    if status is None:
        return "no response"
    if status >= 400:
        return f"http {status}"
    if title.strip() == "":
        return "empty title"
    return "unknown"

async def run() -> Tuple[List[CheckResult], List[CheckResult]]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()

        page = await context.new_page()
        await page.goto(START_URL, wait_until="domcontentloaded")
        await auto_scroll(page)

        univ_links = await extract_univ_links(page)
        await page.close()

        print(f"수집된 링크 수: {len(univ_links)}")

        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        results: List[CheckResult] = []

        start_ts = time.perf_counter()

        async def worker(idx: int, item: UnivLink):
            async with semaphore:
                r = await visit_and_check(context, item)
                results.append(r)
                done = len(results)
                if done % 10 == 0 or done == len(univ_links):
                    elapsed = time.perf_counter() - start_ts
                    remaining = len(univ_links) - done
                    print(f"[progress] {done}/{len(univ_links)} done | elapsed={elapsed:.1f}s | remaining={remaining}")

        await asyncio.gather(*(worker(i, u) for i, u in enumerate(univ_links)))

        await context.close()
        await browser.close()

        problems = [r for r in results if not r.ok]
        return results, problems

async def auto_scroll(page, step: int = 1000, pause_ms: int = 200):
    # 무한 스크롤/지연 로딩 대비(필요 시)
    last_height = await page.evaluate("() => document.body.scrollHeight")
    while True:
        await page.evaluate(f"window.scrollBy(0, {step});")
        await page.wait_for_timeout(pause_ms)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

def save_csv(path: Path, rows: List[CheckResult]):
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "href", "status", "title", "ok", "note"])
        for r in rows:
            writer.writerow([r.name, r.href, r.status if r.status is not None else "", r.title, "Y" if r.ok else "N", r.note])

if __name__ == "__main__":
    all_results, problems = asyncio.run(run())
    save_csv(OUTPUT_ALL, all_results)
    save_csv(OUTPUT_PROBLEM, problems)
    print(f"완료! 전체 {len(all_results)}건 / 문제 {len(problems)}건.\n- {OUTPUT_ALL.resolve()}\n- {OUTPUT_PROBLEM.resolve()}")