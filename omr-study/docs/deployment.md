# Vercel + Supabase Free 배포

현재 기본 배포 구성은 **Vercel 한 프로젝트(React + Python API)**와 **Supabase Free(PostgreSQL + Private Storage)**입니다. Render는 필요하지 않습니다. 무료 사용량 범위 내 운영을 목표로 하며 한도 초과 시 자동 유료 전환을 설정하지 마세요.

## 1. Supabase 프로젝트

1. https://supabase.com/dashboard 에서 Free 프로젝트를 생성합니다. 가능하면 Seoul 지역을 선택합니다.
2. Storage에서 `omr-private` 버킷을 만듭니다. **Public은 끄고**, 파일 크기 제한은 30MB로 설정합니다. 공개 접근 정책은 추가하지 않습니다.
3. 프로젝트의 Connect → Transaction pooler 연결 문자열을 확인합니다. `postgresql://postgres.<ref>:<password>@...pooler.supabase.com:6543/postgres?sslmode=require` 형식입니다. 비밀번호에 특수문자가 있으면 URL 인코딩합니다.
4. Project URL과 서버 전용 `service_role` 키를 확인합니다. 이 키는 브라우저 코드에 넣거나 채팅/Git에 올리지 않습니다.

## 2. Vercel 프로젝트

- 기존 사이트와 별도 프로젝트를 생성합니다.
- 저장소: `twoosun/pass-it-webgame`
- 소스 브랜치: `deploy/omr-study` (현재 main에는 OMR 코드가 없습니다.)
- **Root Directory: `omr-study`** — `omr-study/frontend`가 아닙니다.
- Framework Preset: Other
- 코드의 `vercel.json`이 설치/빌드/출력 폴더/API 경로를 지정합니다. 별도 Render 주소나 API 프록시가 필요하지 않습니다.
- 자동 Git 배포는 연결 설정 전 실패하는 배포를 방지하도록 꺼 두었습니다. 최초 배포는 CLI/API로 수행합니다. 환경변수 검증 후 자동 배포를 원하면 `vercel.json`의 `git.deploymentEnabled`를 변경합니다.
- Fluid Compute를 활성화합니다. 페이지별 함수 최대 실행 시간은 300초입니다.
- Hobby 계정의 비상업적 개인 사용 및 무료 한도에 맞게 사용합니다.

Vercel 프로젝트의 Environment Variables에 다음 값을 등록합니다. 서버용 이름을 그대로 사용하며 `VITE_` 접두사를 붙이지 않습니다.

| 이름 | 값 |
|---|---|
| `DATABASE_URL` | Supabase transaction pooler PostgreSQL 연결 문자열, SSL 포함 |
| `SUPABASE_URL` | Supabase 프로젝트 HTTPS URL |
| `SUPABASE_SERVICE_ROLE_KEY` | 서버 전용 service_role 키 |
| `SUPABASE_BUCKET` | `omr-private` |

Production에 등록합니다. Preview에도 연결하면 같은 DB를 사용할 수 있으므로 필요할 때만 선택하세요. 별도 도메인을 연결한 경우 `OMR_PUBLIC_ORIGIN`에 그 HTTPS origin을 설정합니다. Vercel 기본 배포/프로덕션 도메인은 자동 허용합니다.

Vercel CLI로 로컬에서 배포할 때도 작업 폴더는 `omr-study`입니다. 최초 로그인 및 새 프로젝트 연결은 계정 소유자가 수행해야 합니다. 유료 업그레이드는 필요 시 별도로 결정하며 이 구성에서 자동 생성하지 않습니다.

## 동작과 보관

- PostgreSQL의 비공개 `omr` 스키마에 로그인·시험·채점·파일 메타데이터를 보관합니다. 서버 시작 시 advisory lock으로 테이블 생성/추가 컬럼 마이그레이션을 직렬화합니다.
- Vercel에 DB 설정이 없으면 임시 SQLite로 조용히 대체하지 않고 시작을 거절합니다.
- 로그인한 사용자가 일회 업로드용 경로를 발급받아 Storage에 직접 전송합니다. 다운로드는 소유권을 확인한 뒤 5분짜리 URL로 전달합니다. Public 버킷은 거절합니다.
- 원본 크기를 서버에서 재확인하고 파일 형식을 검사한 뒤 완료 처리합니다. PDF는 1~30페이지, 파일당 30MB까지입니다.
- PDF를 한 페이지씩 요청하므로 전체 30페이지 분석을 한 함수 실행에 몰아넣지 않습니다. `/tmp`는 처리 중에만 사용하고 요청 후 제거합니다.
- 백업은 파일들을 브라우저로 개별 다운로드해 기존 JSON 형식으로 조립합니다. 복구는 이미지들을 직접 업로드한 뒤 시험별 메타데이터를 저장합니다. 대용량 이미지를 함수 요청/응답 본문에 넣지 않습니다.
- 기존 로컬 기록은 설정 → JSON 백업으로 내보내고 공개 사이트에서 복구합니다.

## 공개 후 검증

`/api/health` 확인 → 회원가입 → 실제 OMR 업로드 → 날짜/단답형 확인 → 일괄 정답 → 일부 오답과 배점 입력 → 저장 → 재로그인 → 이미지/기록 조회 → JSON 백업·복구를 확인합니다. 재배포 뒤에도 같은 기록과 사진이 열려야 합니다.

현재 로컬 자동 테스트는 외부 Storage HTTP를 모의 서비스로 검증합니다. 실제 Vercel 런타임, Supabase PostgreSQL 연결 및 공개 업로드는 계정 연결 후 검증해야 합니다. Linux용 Python 의존성 다운로드 성공만으로 실제 배포 성공을 의미하지 않습니다.

## 참고

- https://vercel.com/docs/functions/limitations
- https://vercel.com/docs/functions/runtimes/python
- https://supabase.com/docs/guides/database/connecting-to-postgres
- https://supabase.com/docs/guides/troubleshooting/using-sqlalchemy-with-supabase-FUqebT
- https://supabase.com/pricing

`deploy/render.yaml`은 이전의 선택 가능한 유료 서버 예시이며 현재 Vercel 배포에는 사용하지 않습니다.

로컬 `.env.vercel.local`에 네 값을 입력하고 `python deploy/configure_vercel.py`를 실행하면 Supabase 연결과 비공개 버킷을 확인하고 Vercel의 `omr-study` 프로젝트에 Production 서버 환경변수로 등록합니다. 버킷이 없으면 비공개로 생성합니다. 이 스크립트는 키를 출력하지 않습니다.
