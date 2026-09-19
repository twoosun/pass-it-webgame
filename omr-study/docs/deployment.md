# 공개 배포 준비

현재 로컬 프로그램은 로그인·OpenCV·SQLite·업로드 파일을 사용하는 통합 앱입니다. Vercel에서는 기존 사이트와 다른 **새 프로젝트**를 만들면 됩니다. 기존 Vercel 프로젝트를 덮어쓰지 않습니다.

## 준비된 경로

- 화면: Vercel의 별도 Vite 프로젝트, Root Directory `omr-study/frontend`.
- Python/저장소: Docker 웹 서비스 + 영구 디스크. 기존 `Dockerfile`로 프런트까지 포함한 통합 서비스도 실행할 수 있습니다.
- Vercel `/api/*`는 Python 서버로 외부 rewrite합니다. 브라우저는 같은 Vercel 주소로 로그인/파일 요청을 보내므로 쿠키를 별도 도메인에 공유할 필요가 없습니다.
- Python 서버의 `OMR_PUBLIC_ORIGIN`은 실제 공개 Vercel origin 하나만 지정합니다. `OMR_HTTPS=1`로 Secure 세션 쿠키를 사용합니다.
- SQLite와 업로드 파일은 `OMR_DATA_DIR`에 저장하고 반드시 영구 디스크에 연결합니다. 서버 재배포 때 날아가는 임시 파일시스템에 기록을 보관하지 않습니다.

## 배포 순서

1. 호스팅 계정을 연결하고 Python 서버/영구 저장소를 마련합니다. `deploy/render.yaml`은 별도의 Render 서비스 설정 예시입니다. 이 구성의 서버·디스크는 유료이므로 비용 승낙 없이 생성하지 않습니다.
2. 서버의 `/api/health`가 `{"ok":true,"service":"omr-study"}`를 반환하는지 확인합니다.
3. 프로젝트 폴더에서 `python deploy/prepare_vercel.py "실제 Python 서버 HTTPS 주소"`를 실행합니다. 상태 확인에 성공한 실제 주소로만 `frontend/vercel.json`을 생성합니다.
4. Vercel에서 새 프로젝트를 만들고 Root Directory를 `omr-study/frontend`로 지정합니다. Build Command는 `npm run build`, Output Directory는 `dist`입니다.
5. 배포된 Vercel origin을 Python 서버의 `OMR_PUBLIC_ORIGIN`에 설정합니다.
6. 공개 주소에서 회원가입 → OMR 업로드 → 날짜 확인 → 모두 정답 → 오답 체크/배점 → 저장 → 다시 조회를 확인합니다.

서버를 Vercel Python Functions에 직접 배포하는 방식을 선택한다면 SQLite/로컬 파일 보관을 PostgreSQL/객체 저장소로 교체하고, 업로드 크기 및 실행 제약에 맞게 업로드 경로를 추가 변경해야 합니다. 현재 코드를 정적 화면만 올려서 전체 서비스가 배포된 것으로 보고하지 않습니다.

실제 업로드/DB/비밀번호/세션은 Git 또는 Vercel 프런트 빌드에 포함하지 않습니다. `.gitignore`와 `.dockerignore`를 적용한 소스만 사용합니다.

참고: [Vercel 프로젝트 제한](https://vercel.com/docs/limits), [외부 rewrite](https://vercel.com/docs/routing/rewrites), [Render 영구 디스크](https://render.com/docs/disks).
