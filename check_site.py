import requests
import csv
from datetime import datetime
import os



# 현재 시각으로 결과 파일명 생성
now = datetime.now().strftime("%Y%m%d_%H%M")
RESULT_DIR = "c:\\projects\\ScriptSite\\result\\"
INPUT_CSV = os.path.join(RESULT_DIR, "jinhak_ac_kr_links_20250829_1415.csv")
OUTPUT_CSV = os.path.join(RESULT_DIR, f"jinhak_ac_kr_links_check_{now}.csv")

def check_url(url: str) -> str:
    try:
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            return "OK"
        else:
            return f"Error {response.status_code}"
    except requests.exceptions.RequestException as e:
        return f"Error: {e.__class__.__name__}"

results = []

# CSV 읽고 확인
with open(INPUT_CSV, newline="", encoding="utf-8-sig") as infile:
    reader = csv.reader(infile)
    header = next(reader)  # 첫 줄은 헤더
    for row in reader:
        if len(row) < 2:
            continue
        school, url = row[0], row[1]
        status = check_url(url)
        print(f"{school} | {url} -> {status}")
        results.append([school, url, status])

# 결과 CSV 저장
with open(OUTPUT_CSV, "w", newline="", encoding="utf-8-sig") as outfile:
    writer = csv.writer(outfile)
    writer.writerow(["학교명", "링크", "결과"])
    writer.writerows(results)

print(f"결과 저장 완료: {OUTPUT_CSV}")
