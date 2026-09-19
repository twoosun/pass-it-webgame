# 실모실록

제공된 **2026학년도 수능 답안지 PDF의 1~3페이지**를 기준으로 만든 국어·수학·영어 OMR 인식 프로그램입니다. Python OpenCV 엔진을 tkinter 데스크톱과 FastAPI/React 웹이 공유합니다. 원본 프로젝트와 독립적인 `omr-study` 폴더에 구성했습니다.

공개 사이트: **https://silsil.vercel.app** (Vercel + Supabase). 새 계정을 만들어 사용할 수 있습니다. 로컬 기록은 JSON 백업·복구로 옮깁니다.

## 실행

Windows에서 Python 3.12 이상을 설치하고 이 폴더에서 실행합니다. 이 환경에서는 Python 3.14.4로 검사했습니다. 최초 웹 빌드에는 Node.js 20.19+/22.12+가 필요합니다. 이미 `frontend/dist`가 있으면 Node.js 없이도 웹 서버가 실행됩니다.

```powershell
cd C:\Users\Admin\passit\omr-study
python -m pip install -r requirements.txt
python run.py
```

접속: **http://127.0.0.1:8000**. 회원가입 후 사용합니다. 기본 계정이나 비밀번호는 없습니다. SQLite DB는 `data/app.db`, 사용자 파일은 `data/uploads`에 저장합니다. 기본 서버는 로컬 컴퓨터에서만 접근할 수 있습니다.

데스크톱:

```powershell
python main.py
python main.py --debug
```

명령행 분석:

```powershell
python main.py "촬영본.jpg" "영어.png" --debug --output output/results.json
python main.py "답안.pdf" --output output/results.csv
```

PDF는 페이지별로 분석합니다. JPG/JPEG/PNG 및 EXIF 회전을 지원합니다. 이미지 최대 50MP, 웹 파일당 30MB, PDF당 30페이지입니다. 실패한 페이지는 오류와 빈 답안으로 반환하고 다른 페이지는 계속 처리합니다.

## 처음 사용하는 순서

1. 회원가입 → 새 시험 → 시험 이름·회차·날짜·종류 입력.
2. OMR 파일을 업로드합니다. 별도 이미지 여러 장 또는 다중 페이지 PDF를 사용할 수 있습니다.
3. 과목·날짜·답안을 확인하고 노란색 문항을 클릭해 실제 마킹 crop과 판독 점수를 비교합니다. 객관식은 선택 상자, 수학 단답형은 숫자 입력으로 수정합니다.
4. 문항별 정답/오답 체크박스로 채점합니다. 과목별 모두 정답·모두 오답·체크 초기화 버튼도 제공합니다. 별도 정답지 업로드나 정답 입력은 필요하지 않습니다.
5. 오답 문항에만 배점을 입력합니다. 모든 문항을 체크하고 오답 배점을 입력하면 **100 − 오답 배점 합계**로 원점수를 계산합니다. 미체크나 배점 누락 시 점수는 미완성으로 표시합니다. 표준점수·백분위·등급·풀이 시간은 별도로 입력합니다.
6. 기록 저장 → 시험 목록·대시보드·오답·성적 분석에 반영됩니다. 정답으로 수정한 문항은 오답 목록에서 즉시 제외됩니다.
7. 오답에 메모·태그·복습 상태·즐겨찾기를 지정합니다. 시험지 PDF를 별도로 첨부하고 오답의 페이지 번호를 지정해 해당 페이지를 열 수 있습니다.

현재 편집 내용은 **사용자별 브라우저 localStorage에 자동 보관**됩니다. `임시 저장`은 서버에 DRAFT로, `기록 저장`은 COMPLETED로 저장합니다. 기기를 바꿀 때는 서버 저장을 누르세요. 다른 창에서 수정한 이전 버전으로 덮어쓰는 요청은 409로 거절합니다.

## 실제 템플릿 구조

PDF는 벡터/텍스트가 없는 래스터 문서입니다. 원본 페이지는 841.92 × 595.20 pt 가로형이며, 각 페이지를 **2526 × 1786 px (216dpi)** PNG로 추출했습니다.

| 과목 | 객관식 배치 | 단답형 |
|---|---|---|
| 국어 | 1~20 / 21~34 / 35~45 | 없음 |
| 수학 | 1~10 / 11~15 / 23~28 | 16~22 / 29~30, 백·십·일 3열 |
| 영어 | 1~20 / 21~40 / 41~45 | 없음 |

수학 백의 자리에는 0 버블이 없습니다. 빈 앞자리는 허용하지만 중간/끝의 빈 자리를 임의로 0으로 채우지 않습니다. 예: `[BLANK,2,4] → 24`, `[1,BLANK,8] → ?`.

좌표와 기준 마커는 `config/templates.json`에 정규화 좌표로 저장합니다. 상세 측정값은 `docs/template-analysis.json`을 참고하세요.

## 날짜와 가상 숫자 위치

수험번호의 가운데 구분 칸은 건너뛰고 **8개 숫자 열을 YYYYMMDD로 사용**합니다. 각 열의 실제 버블 존재 여부와 관계없이 0~9 좌표를 모두 저장합니다.

- `20260930` → OMR 화면 `2026-0930`, DB `2026-09-30`.
- 실제 버블이 없는 끝에서 두 번째 열의 3 위치에도 검게 마킹할 수 있습니다.
- 가상 위치는 측정한 숫자 행 간격의 중앙값으로 보간·외삽합니다. 좌표 GUI에서 주황색으로 볼 수 있습니다.
- 기준 템플릿과 정렬한 뒤 차영상을 계산하므로 원래 인쇄된 숫자·선과 추가 마킹을 분리합니다.
- 불확실한 자리는 `?`, 복수 마킹은 자리별 `MULTI`입니다. 잘못된 날짜를 달력 규칙에 맞춰 자동 변경하지 않습니다.
- 검정 펜을 사용하고, 가상 위치에서 인접 열/행을 침범하지 않도록 마킹하세요.

날짜는 OMR에서 먼저 읽습니다. 인식 오류나 페이지 간 날짜 불일치가 있으면 직접 날짜를 수정해야 기록을 완료할 수 있습니다. 수정 전에도 임시 저장할 수 있습니다.

## 판독 방식과 품질 검사

1. SIFT 인쇄 특징점으로 세 과목을 비교합니다. 색상이나 PDF 페이지 순서로만 과목을 결정하지 않습니다.
2. 중복 대응점을 제거하고 RANSAC homography로 원근·회전을 보정합니다.
3. ECC affine 미세 정렬을 수행합니다. 수학 단답형은 인쇄 격자를 기준으로 문항별 국소 정렬을 추가해 종이 휨에 의한 위치 오차를 줄입니다. 과도한 보정은 버립니다.
4. 특징점 분포/오차, 검은 타이밍 마커, 인쇄 윤곽 대응률을 검사합니다. 기준 미달이면 **OMR 정렬 실패**로 중단합니다.
5. 국소 조명 보정 및 채널 최댓값으로 색 인쇄·빨간 표시를 억제하고 기준 차영상을 계산합니다.
6. 버블 내부의 전체/중앙 채움, 연결 요소, 차영상 강도와 페이지 내 빈 버블 통계를 결합합니다. 날짜 가상 위치는 주변 offset도 검사합니다.
7. 최상위/차상위 점수의 크기·차이·비율 및 정렬 품질로 `OK/BLANK/MULTI/UNKNOWN`을 구분합니다.

confidence는 **경험적 품질 지표이며 정답일 확률로 보정된 값은 아닙니다**. 매우 연한 마킹, 심한 구김·흐림·가려짐은 재확인 또는 재촬영이 필요합니다. 다른 연도/양식의 OMR은 지원을 보장하지 않습니다.

## 좌표 자동 추출 / 수동 보정

이미 원본 PDF로 생성한 템플릿 PNG와 좌표 JSON을 포함했습니다. 다시 생성하려면:

```powershell
python calibration/calibrate.py "D:\다운로드\2026학년도 대학수학능력시험 답안지 (OMR 카드) 고화질.pdf"
python calibration/calibration_gui.py
```

자동 추출은 해당 PDF에서 실측한 블록 범위로 문항 의미를 구분하고, 각 버블 중심·행·열은 래스터 윤곽에서 측정합니다. 범용 OMR 양식 자동 해석기가 아닙니다. 예상 행/열 수가 다르면 잘못된 좌표를 저장하지 않고 실패합니다.

수동 GUI: 드래그=개별 이동, Shift+드래그=행 이동, Ctrl+드래그=열 이동, 오른쪽 드래그=pan, 휠=zoom. 좌표 추가·삭제·되돌리기·저장을 지원합니다. 날짜의 80개 좌표나 필수 답안 좌표가 빠지면 저장을 거절합니다. 이전 JSON을 `templates.backup.json`에 보관합니다. 웹은 저장 후 서버 재시작이 필요합니다.

## 디버그

데스크톱은 분석마다 별도 폴더에 디버그 이미지를 보관합니다. 명령행에서는 `--debug`를 지정하세요.

```text
output/debug/<작업>/page_1/
  original.png
  warped.png
  aligned.png
  threshold.png
  difference.png
  roi_overlay.png
  result_overlay.png
  q1.png ...
  result.json
```

GUI의 단계 선택으로 이미지를 전환할 수 있습니다. 문항을 선택하면 crop과 보기별 점수를 표시하고, 날짜 점수 버튼으로 8자리 각각의 0~9 점수를 확인할 수 있습니다. 웹 디버그 이미지도 인증된 사용자만 읽을 수 있습니다.

## 웹 개발 / Docker

통합 실행은 `python run.py` 한 명령입니다. 프런트엔드를 수정했다면 다시 빌드하고 서버를 재시작하세요.

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
python run.py
```

개발 서버 두 개를 별도로 실행할 수도 있습니다.

```powershell
# 프로젝트 루트, 첫 터미널
python -m uvicorn backend.main:app --reload --port 8000
# 두 번째 터미널
cd frontend
npm.cmd run dev
# http://localhost:3000 (Vite가 /api를 백엔드로 전달)
```

```powershell
docker compose up --build
```

Docker 구성은 제공했지만 이 환경에서 Docker 실행은 검증하지 않았습니다. SQLAlchemy를 사용하므로 `DATABASE_URL`을 PostgreSQL 연결 문자열로 지정하고 해당 DB 드라이버를 설치할 수 있습니다. PostgreSQL 이전은 별도 검증이 필요합니다.

## 인증 / 데이터 보관

비밀번호는 개별 salt와 scrypt로 해시합니다. 서버에는 세션 토큰의 SHA-256 해시만 저장합니다. 쿠키는 HttpOnly/SameSite=Strict, 30일 세션입니다. 모든 시험·문항·파일 API는 사용자 소유권을 확인합니다. 외부 Origin의 쓰기 요청을 거절합니다. 외부 배포 시 HTTPS를 구성하고 `OMR_HTTPS=1`을 설정하세요.

설정에서 JSON 전체 백업·복구, 전체/수학/오답 CSV 내보내기를 제공합니다. JSON에는 연결된 원본·정렬·crop·시험지 파일도 포함되므로 용량이 커질 수 있습니다. 복구는 UUID를 기준으로 중복을 건너뛰고 사용자별 새 파일 ID를 발급합니다. CSV는 Excel 수식 실행을 막도록 문자열을 이스케이프합니다. 가장 간단한 로컬 전체 보관은 서버를 종료한 뒤 `data` 폴더를 복사하는 방법입니다.

## 테스트

```powershell
python -m compileall -q omr backend calibration main.py run.py
python -m pytest -q
node --experimental-strip-types --test tests/manual-grading.test.mjs
```

테스트는 임시 DB에 실행되며 실제 `data/app.db` 계정/기록을 변경하지 않습니다. 검증 내용과 한계는 `docs/verification.md`에 기록했습니다.

## 파일 구성

```text
main.py / run.py             데스크톱 / 웹 실행
omr/                        공통 인식 엔진
calibration/                자동 좌표 추출 / 수동 편집
config/templates.json       정규화 좌표, 기준 마커, PDF 해시
assets/template_*.png       제공된 PDF 1~3페이지 이미지
backend/                    API, SQLAlchemy 모델, 검증, 채점
frontend/                   React + TypeScript + Recharts
tests/                      OMR/웹/접근권한/복구 테스트
docs/                       구조 분석과 검증 기록
```

## 공개 배포

Vercel(화면 + Python API)과 Supabase Free(DB + 비공개 파일 저장소)를 연결하는 절차는 [배포 안내](docs/deployment.md)를 참고하세요. 로컬 실행만으로 인터넷에 공개되지는 않습니다.
