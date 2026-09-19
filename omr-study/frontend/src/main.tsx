import { analyzeUpload, uploadAttachment, exportBackup, importBackup } from "./cloud";
import type { Question } from "./manualGrading";
import React, { useState, useEffect } from "react";
import { createRoot } from "react-dom/client";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import "./style.css";
import { gradingOutcome, gradeQuestion, gradingSummary, applyRecognizedDates } from "./manualGrading";

type Any = Record<string, any>;
const labels: Any = { korean: "국어", math: "수학", english: "영어" };
const states: Any = {
  CORRECT: "정답",
  WRONG: "오답",
  BLANK: "미응답",
  MULTI: "복수 마킹",
  UNKNOWN: "확인 필요",
  UNGRADED: "미채점",
};
const kinds = [
  "평가원",
  "교육청",
  "수능",
  "사설 모의고사",
  "학교 시험",
  "기타",
];
const reviews = ["미복습", "복습 중", "해결", "다시 볼 문제"];
const tags = [
  "개념 부족",
  "계산 실수",
  "조건 누락",
  "시간 부족",
  "찍음",
  "문제 해석 오류",
  "선지 판단 오류",
  "풀이 방향 오류",
  "마킹 실수",
];
const numeric = (s: string, n: number) =>
  s === "math" && ((n >= 16 && n <= 22) || n >= 29);
const today = () => new Date().toLocaleDateString("sv-SE");
const outcome = (q:Any) => gradingOutcome(q as Question);
async function api(url: string, options: RequestInit = {}) {
  const r = await fetch("/api" + url, {
    ...options,
    headers:
      options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" },
    credentials: "same-origin",
  });
  const data = await r.json().catch(() => ({ detail: r.statusText }));
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  return data;
}
const send = (url: string, data: unknown, method = "POST") =>
  api(url, { method, body: JSON.stringify(data) });
function go(path: string) {
  location.hash = path;
}
function download(data: unknown, name: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
const icons: Record<string, React.ReactNode> = {
  dashboard: <><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></>,
  exams: <><path d="M6 3h12a2 2 0 0 1 2 2v16H4V5a2 2 0 0 1 2-2Z"/><path d="M8 8h8M8 12h8M8 16h5"/></>,
  new: <><rect x="3" y="3" width="18" height="18" rx="3"/><path d="M12 7v10M7 12h10"/></>,
  wrong: <><path d="M5 4h14v16H5zM8 8h8M8 12h8M8 16h5"/></>,
  retry: <><path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/></>,
  stats: <><path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/></>,
  settings: <><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.6v.2h-4V21a1.7 1.7 0 0 0-1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3 14H2.8v-4H3a1.7 1.7 0 0 0 1.6-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1a1.7 1.7 0 0 0 1.9.3A1.7 1.7 0 0 0 10 3V2.8h4V3a1.7 1.7 0 0 0 1 1.6 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.6 1h.2v4H21a1.7 1.7 0 0 0-1.6 1Z"/></>,
};
function Icon({ name }: { name: string }) {
  return <svg className="nav-icon" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">{icons[name]}</svg>;
}
function Field({ label, children }: any) {
  return (
    <label className="field">
      <span>{label}</span>
      {children}
    </label>
  );
}
function Empty({ children }: any) {
  return (
    <div className="empty">
      <span className="empty-icon">▤</span>
      <h3>{children}</h3>
      <p>기록이 쌓이면 변화가 보입니다.</p>
    </div>
  );
}
function SubjectSelect({ value, onChange, all = true }: any) {
  return (
    <select
      aria-label="과목"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {all && <option value="">전체 과목</option>}
      {Object.entries(labels).map(([k, v]) => (
        <option key={k} value={k}>
          {v as string}
        </option>
      ))}
    </select>
  );
}
function App() {
  const [user, setUser] = useState<Any | null>(null),
    [loading, setLoading] = useState(true),
    [route, setRoute] = useState(location.hash.slice(1) || "dashboard"),
    [error, setError] = useState("");
  useEffect(() => {
    api("/auth/me")
      .then(setUser)
      .catch(() => {})
      .finally(() => setLoading(false));
    const f = () => {
      setRoute(location.hash.slice(1) || "dashboard");
      setError("");
    };
    window.addEventListener("hashchange", f);
    return () => window.removeEventListener("hashchange", f);
  }, []);
  const fail = (e: any) => setError(e.message || String(e));
  if (loading) return <div className="loading">기록을 불러오는 중…</div>;
  if (!user) return <Auth onLogin={setUser} />;
  const menu = [
    ["dashboard", "대시보드"],
    ["exams", "시험 기록"],
    ["new", "새 시험"],
    ["wrong", "오답 노트"],
    ["retry", "다시 풀기"],
    ["stats", "성적 분석"],
    ["settings", "설정"],
  ];
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="#dashboard">
          <span>
            실모실록<small>실전 모의고사 학습 기록</small>
          </span>
        </a>
        <div className="nav-caption">학습 관리</div>
        <nav>
          {menu.map(([id, name]) => (
            <a
              key={id}
              className={route.split("/")[0] === id ? "active" : ""}
              href={"#" + id}
            >
              <Icon name={id} />
              <span className="nav-label">{name}</span>
            </a>
          ))}
        </nav>
        <a className="profile" href="#settings">
          <div className="avatar">{user.username.slice(0, 1)}</div>
          <div>
            <strong>{user.username}</strong>
            <small>나의 공부 기록</small>
          </div>
        </a>
      </aside>
      <main>
        <header className="topbar">
          <span className="topbar-title">오늘의 공부도 차곡차곡 기록해 보세요.</span>
          <span>
            {today().replaceAll("-", ".")} <a className="topbar-user" href="#settings">{user.username}</a>
          </span>
        </header>
        {error && (
          <div className="error" role="alert">
            {error}
            <button onClick={() => setError("")}>닫기</button>
          </div>
        )}
        {route === "dashboard" ? (
          <Dashboard fail={fail} />
        ) : route === "exams" ? (
          <ExamList fail={fail} />
        ) : route === "new" || route.startsWith("exam/") ? (
          <Editor
            key={route}
            id={route.split("/")[1]}
            user={user}
            fail={fail}
          />
        ) : route === "wrong" || route === "retry" ? (
          <Wrong key={route} retry={route === "retry"} fail={fail} />
        ) : route.startsWith("wrong/") ? (
          <WrongDetail id={route.split("/")[1]} fail={fail} />
        ) : route === "stats" ? (
          <Stats fail={fail} />
        ) : (
          <Settings user={user} setUser={setUser} fail={fail} />
        )}
      </main>
    </div>
  );
}
function Auth({ onLogin }: any) {
  const [register, setRegister] = useState(false),
    [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [username, setUsername] = useState(""),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <div className="auth">
      <section className="auth-story">
        <div className="brand">
          실모실록
        </div>
        <p className="eyebrow">YOUR STUDY, CLEARLY.</p>
        <h1>
          풀었던 한 장이,
          <br />
          다음의 실력이 되도록.
        </h1>
        <p>
          답안 인식부터 오답 복습까지.
          <br />
          흩어진 시험 기록을 한곳에 모으세요.
        </p>
        <div className="paper-art">
          <div>
            나의 공부 기록 <span>↗</span>
          </div>
          <hr />
          <p>OMR 인식 → 답안 확인 → 오답 복습</p>
          <div className="art-dots">
            ● ○ ○ ○ ○<br />○ ○ ● ○ ○<br />○ ● ○ ○ ○
          </div>
        </div>
      </section>
      <section className="auth-form">
        <div>
          <p className="eyebrow">WELCOME TO OMR STUDY</p>
          <h2>
            {register ? "공부 기록을 시작하세요" : "다시 만나서 반가워요"}
          </h2>
          <p className="muted">
            {register
              ? "나만의 학습 아카이브를 만드세요."
              : "오늘의 기록을 이어가세요."}
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                onLogin(
                  await send("/auth/" + (register ? "register" : "login"), {
                    email,
                    password,
                    username: username || "수험생",
                  }),
                );
              } catch (e: any) {
                setError(e.message);
              } finally {
                setBusy(false);
              }
            }}
          >
            <Field label="아이디 또는 이메일">
              <input
                required
                autoComplete="username"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </Field>
            {register && (
              <Field label="닉네임">
                <input
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                />
              </Field>
            )}
            <Field label="비밀번호">
              <input
                required
                minLength={8}
                type="password"
                autoComplete={register ? "new-password" : "current-password"}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </Field>
            {error && <p className="error">{error}</p>}
            <button className="primary wide" disabled={busy}>
              {busy ? "처리 중…" : register ? "회원가입" : "로그인"}{" "}
              <span>→</span>
            </button>
          </form>
          <button
            className="link"
            onClick={() => {
              setRegister(!register);
              setError("");
            }}
          >
            {register
              ? "이미 계정이 있나요? 로그인"
              : "처음 오셨나요? 회원가입"}
          </button>
        </div>
      </section>
    </div>
  );
}
function Heading({ eyebrow, title, description, action }: any) {
  return (
    <div className="heading">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h1>{title}</h1>
        <p className="muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
function StudyCalendar({ exams }: { exams: Any[] }) {
  const initial = exams.find((exam) => exam.exam_date)?.exam_date || today();
  const [month, setMonth] = useState(() => initial.slice(0, 7));
  const [year, monthNumber] = month.split("-").map(Number);
  const firstDay = new Date(year, monthNumber - 1, 1).getDay();
  const lastDate = new Date(year, monthNumber, 0).getDate();
  const dates = new Map<string, Any[]>();
  for (const exam of exams) {
    if (!exam.exam_date?.startsWith(month)) continue;
    dates.set(exam.exam_date, [...(dates.get(exam.exam_date) || []), exam]);
  }
  const move = (offset: number) => {
    const next = new Date(year, monthNumber - 1 + offset, 1);
    setMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}`);
  };
  return (
    <section className="panel calendar-panel">
      <div className="section-title calendar-title">
        <h2>학습 달력</h2>
        <div className="calendar-controls">
          <button aria-label="이전 달" onClick={() => move(-1)}>‹</button>
          <strong>{year}년 {monthNumber}월</strong>
          <button aria-label="다음 달" onClick={() => move(1)}>›</button>
        </div>
      </div>
      <div className="calendar-weekdays">
        {["일", "월", "화", "수", "목", "금", "토"].map((day) => <span key={day}>{day}</span>)}
      </div>
      <div className="calendar-grid">
        {Array.from({ length: firstDay }, (_, index) => <span key={`blank-${index}`} />)}
        {Array.from({ length: lastDate }, (_, index) => {
          const day = index + 1;
          const date = `${month}-${String(day).padStart(2, "0")}`;
          const records = dates.get(date) || [];
          const current = date === today();
          return (
            <span className={`${records.length ? "recorded" : ""} ${current ? "today" : ""}`} key={date} title={records.map((exam) => exam.name).join(", ")}>
              <b>{day}</b>{records.length > 0 && <i>{records.length}</i>}
            </span>
          );
        })}
      </div>
      <p className="calendar-legend"><i /> 실모 기록이 있는 날 <span>{dates.size}일</span></p>
    </section>
  );
}
function Dashboard({ fail }: any) {
  const [exams, setExams] = useState<Any[]>([]),
    [wrong, setWrong] = useState<Any[]>([]),
    [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState(false);
  useEffect(() => {
    Promise.all([api("/exams"), api("/wrong-answers")])
      .then(([e, w]) => {
        setExams(e);
        setWrong(w);
      })
      .catch((error) => { setLoadError(true); fail(error); })
      .finally(() => setLoading(false));
  }, []);
  if (loading) return <section className="panel" role="status">시험 기록을 불러오는 중입니다…</section>;
  if (loadError) return <section className="panel" role="alert">기록을 불러오지 못했습니다. <button onClick={() => location.reload()}>다시 불러오기</button></section>;
  return (
    <>
      <Heading
        eyebrow="STUDY OVERVIEW"
        title="차곡차곡, 나의 공부 기록"
        description="지난 시험을 돌아보고, 다음 한 걸음을 준비하세요."
        action={
          <button className="primary" onClick={() => go("new")}>
            ＋ 새 시험 기록
          </button>
        }
      />
      <section className="summary-grid">
        <div className="metric">
          <span>기록한 시험</span>
          <strong>
            {exams.length}
            <small>회</small>
          </strong>
          <p>나의 학습 여정</p>
        </div>
        {Object.keys(labels).map((s) => {
          const recent = exams.find((e) =>
            e.subjects.some((x: Any) => x.subject === s),
          );
          const record = recent?.subjects.find((x: Any) => x.subject === s);
          return (
            <div className="metric" key={s}>
              <span>최근 {labels[s]} 점수</span>
              <strong>
                {record?.display_score ?? "—"}
                <small>점</small>
              </strong>
              <p>
                {recent
                  ? recent.exam_date + " · " + recent.name
                  : "첫 기록을 기다리고 있어요"}
              </p>
            </div>
          );
        })}
      </section>
      <div className="dashboard-columns">
        <section className="panel">
          <div className="section-title">
            <h2>최근 시험</h2>
            <a href="#exams">전체 보기 →</a>
          </div>
          {!exams.length ? (
            <Empty>아직 시험 기록이 없어요</Empty>
          ) : (
            exams.slice(0, 5).map((e) => <ExamCard key={e.id} exam={e} />)
          )}
          <div className="subtle">
            {exams[0]
              ? "최근 시험일 · " + exams[0].exam_date
              : "OMR을 업로드하면 답안을 자동으로 읽어드려요."}
          </div>
        </section>
        <div className="dashboard-side">
          <StudyCalendar exams={exams} />
          <section className="panel">
            <div className="section-title">
              <h2>다시 살펴볼 문제</h2>
              <a href="#retry">복습하기 →</a>
            </div>
            <div className="review-count">
              <strong>{wrong.filter((q) => q.review_status === "미복습").length}</strong><span>미복습 오답</span>
              <strong>{wrong.filter((q) => q.review_status === "다시 볼 문제").length}</strong><span>다시 볼 문제</span>
            </div>
            {wrong.length ? wrong.slice(0, 3).map((q) => (
              <a className="recent-wrong" key={q.id} href={"#wrong/" + q.id}>
                <b>{labels[q.subject]} {q.number}번</b><span>{q.exam_name} {q.round}</span><small>{states[q.outcome]} →</small>
              </a>
            )) : <Empty>복습할 오답이 없어요</Empty>}
          </section>
        </div>
      </div>
      <section className="panel">
        <h2>최근 5회 성적</h2>
        <div className="three">
          {Object.keys(labels).map((s) => (
            <div key={s}>
              <p>{labels[s]}</p>
              <strong className="score-sequence">
                {exams
                  .filter((e) => e.subjects.some((x: Any) => x.subject === s))
                  .slice(0, 5)
                  .reverse()
                  .map(
                    (e) =>
                      e.subjects.find((x: Any) => x.subject === s)
                        ?.display_score ?? "—",
                  )
                  .join(" → ") || "—"}
              </strong>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
function ExamCard({ exam: e }: any) {
  return (
    <a className="exam-card" href={"#exam/" + e.id}>
      <div className="date-block">
        {e.exam_date.slice(5).replace("-", ".")}
        <small>{e.exam_date.slice(0, 4)}</small>
      </div>
      <div className="grow">
        <div>
          <span className="badge">{e.exam_type}</span>
          {e.state === "DRAFT" && (
            <span className="badge amber">임시 저장</span>
          )}
        </div>
        <h3>
          {e.name} <small>{e.round}</small>
        </h3>
        {e.subjects.length ? <div className="exam-subjects">
          {e.subjects.map((s: Any) => <span key={s.subject}>
            <b>{labels[s.subject]}</b><strong>{s.display_score ?? "—"}<small>{s.display_score == null ? "미채점" : "점"}</small></strong><em>오답 {s.wrong_count}</em>
          </span>)}
        </div> : <p>OMR 업로드를 기다리고 있어요</p>}
        {e.subjects.some((s: Any) => s.wrong_count > 0) && (
          <p className="wrong-numbers">
            {e.subjects
              .filter((s: Any) => s.wrong_count > 0)
              .map(
                (s: Any) =>
                  `${labels[s.subject]} 오답: ${s.questions
                    .filter(
                      (q: Any) =>
                        q.outcome === "WRONG",
                    )
                    .map((q: Any) => q.number)
                    .join(", ")}`,
              )
              .join(" / ")}
          </p>
        )}
      </div>
      <span>↗</span>
    </a>
  );
}
function ExamList({ fail }: any) {
  const [data, setData] = useState<Any[]>([]),
    [loading, setLoading] = useState(true),
    [loadError, setLoadError] = useState(false),
    [search, setSearch] = useState(""),
    [subject, setSubject] = useState(""),
    [kind, setKind] = useState(""),
    [sort, setSort] = useState("latest"),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [compare, setCompare] = useState<string[]>([]);
  useEffect(() => {
    let active = true;
    setLoading(true);
    setLoadError(false);
    const t = setTimeout(
      () =>
        api(
          "/exams?" +
            new URLSearchParams({
              search,
              subject,
              exam_type: kind,
              sort,
              date_from: from,
              date_to: to,
            }),
        )
          .then((records) => { if (active) setData(records); })
          .catch((error) => { if (active) { setLoadError(true); fail(error); } })
          .finally(() => { if (active) setLoading(false); }),
      180,
    );
    return () => { active = false; clearTimeout(t); };
  }, [search, subject, kind, sort, from, to]);
  return (
    <>
      <Heading
        eyebrow="EXAM ARCHIVE"
        title="시험 기록"
        description="한 번의 시험도 놓치지 않고 기록하세요."
        action={
          <button className="primary" onClick={() => go("new")}>
            ＋ 새 시험
          </button>
        }
      />
      <div className="filters">
        <input
          placeholder="시험 이름 검색"
          aria-label="시험 검색"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <SubjectSelect value={subject} onChange={setSubject} />
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">전체 시험 종류</option>
          {kinds.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
        <select value={sort} onChange={(e) => setSort(e.target.value)}>
          {[
            ["latest", "최신순"],
            ["oldest", "오래된 순"],
            ["name", "시험명"],
            ["korean", "국어 점수"],
            ["math", "수학 점수"],
            ["english", "영어 점수"],
          ].map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select
          aria-label="기간"
          onChange={(e) => {
            setFrom(
              e.target.value
                ? new Date(
                    Date.now() - Number(e.target.value) * 86400000,
                  ).toLocaleDateString("sv-SE")
                : "",
            );
            setTo("");
          }}
        >
          <option value="">전체 기간</option>
          <option value="7">최근 7일</option>
          <option value="30">최근 30일</option>
          <option value="90">최근 3개월</option>
        </select>
        <input
          type="date"
          aria-label="시작일"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <input
          type="date"
          aria-label="종료일"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
      <section className="panel">
        <div className="section-title">
          <h2>{loading ? "기록 불러오는 중…" : loadError ? "기록 조회 실패" : `${data.length}개의 기록`}</h2>
          <span className="muted">두 시험을 체크하면 비교할 수 있어요.</span>
        </div>
        {!loading && !loadError && data.map((e) => (
          <div className="compare-row" key={e.id}>
            <input
              aria-label={e.name + " 비교 선택"}
              type="checkbox"
              checked={compare.includes(e.id)}
              onChange={(ev) =>
                setCompare(
                  ev.target.checked
                    ? [...compare.slice(-1), e.id]
                    : compare.filter((id) => id !== e.id),
                )
              }
            />
            <ExamCard exam={e} />
          </div>
        ))}
        {loading && <p role="status">시험 기록을 불러오고 있습니다. 잠시만 기다려 주세요.</p>}
        {loadError && <p role="alert">기록을 불러오지 못했습니다. <button onClick={() => location.reload()}>다시 불러오기</button></p>}
        {!loading && !loadError && !data.length && <Empty>조건에 맞는 시험이 없어요</Empty>}
      </section>
      {compare.length === 2 && (
        <section className="panel">
          <h2>시험 비교</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>지표</th>
                  {compare.map((id) => (
                    <th key={id}>{data.find((e) => e.id === id)?.name}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {[
                  "점수",
                  "정답률",
                  "오답 개수",
                  "4점 문항 오답",
                  "시간 부족 태그",
                ].map((metric, index) => (
                  <tr key={metric}>
                    <th>{metric}</th>
                    {compare.map((id) => (
                      <td key={id}>
                        {data
                          .find((e) => e.id === id)
                          ?.subjects.map(
                            (s: Any) =>
                              `${labels[s.subject]}: ${[s.display_score ?? "—", s.accuracy == null ? "—" : s.accuracy + "%", s.wrong_count, s.questions.filter((q: Any) => q.outcome === "WRONG" && q.score_value === 4).length, s.questions.filter((q: Any) => q.tags.includes("시간 부족")).length][index]}`,
                          )
                          .join(" / ")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
const emptyExam = () => ({
  name: "",
  round: "",
  exam_date: today(),
  date_needs_review: false,
  date_recognition: "",
  exam_type: "사설 모의고사",
  memo: "",
  state: "DRAFT",
  subjects: [],
  file_ids: [],
});
function blankSubject(subject: string) {
  return {
    subject,
    raw_score: null,
    standard_score: null,
    percentile: null,
    grade: null,
    duration: null,
    first_pass: null,
    questions: Array.from({ length: subject === "math" ? 30 : 45 }, (_, i) => ({
      number: i + 1,
      user_answer: "BLANK",
      correct_answer: null,
      grading_status: null,
      score_value: null,
      confidence: 1,
      category: "",
      note: "",
      review_status: "미복습",
      favorite: false,
      tags: [],
      recognition: {},
    })),
  };
}
function Editor({ id, user, fail }: any) {
  const key = "omr-draft:" + user.id + ":" + (id || "new");
  const [exam, setExam] = useState<Any | null>(null),
    [active, setActive] = useState("math"),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState(""),
    [selected, setSelected] = useState<number | null>(null),
    [onlyWrong, setOnlyWrong] = useState(false),
    [onlyReview, setOnlyReview] = useState(false),
    [preview, setPreview] = useState<Any | null>(null),
    [stage, setStage] = useState("result_overlay");
  useEffect(() => {
    let draft: Any | null = null;
    try {
      draft = JSON.parse(localStorage.getItem(key) || "null");
    } catch {}
    if (id)
      api("/exams/" + id)
        .then((e) => {
          setExam(draft && draft.revision === e.revision ? draft : e);
          setActive(e.subjects[0]?.subject || "math");
        })
        .catch(fail);
    else setExam(draft || emptyExam());
  }, [id]);
  useEffect(() => {
    if (exam) localStorage.setItem(key, JSON.stringify(exam));
  }, [exam, key]);
  const change = (field: string, value: any) =>
    setExam((e: Any) => ({ ...e, [field]: value }));
  const changeSubject = (name: string, value: any) =>
    setExam((e: Any) => ({
      ...e,
      subjects: e.subjects.map((s: Any) =>
        s.subject === active ? { ...s, [name]: value } : s,
      ),
    }));
  const editQuestion = (n: number, field: string, value: any) =>
    setExam((e: Any) => ({
      ...e,
      subjects: e.subjects.map((s: Any) =>
        s.subject === active
          ? {
              ...s,
              questions: s.questions.map((q: Any) =>
                q.number === n
                  ? {
                      ...q,
                      [field]: value,
                      ...(field === "user_answer"
                        ? {
                            confidence: 1,
                            recognition: {
                              ...q.recognition,
                              manually_reviewed: true,
                            },
                          }
                        : {}),
                    }
                  : q,
              ),
            }
          : s,
      ),
    }));
  const grade = (number:number,status:'CORRECT'|'WRONG'|null) => setExam((e:Any)=>({...e,subjects:e.subjects.map((s:Any)=>s.subject===active?{...s,questions:s.questions.map((q:Any)=>q.number===number?gradeQuestion(q as Question,status):q)}:s)}));
  const gradeAll = (status:'CORRECT'|'WRONG'|null) => setExam((e:Any)=>({...e,subjects:e.subjects.map((s:Any)=>s.subject===active?{...s,questions:s.questions.map((q:Any)=>gradeQuestion(q as Question,status))}:s)}));
  async function save(state: string) {
    if (!exam) return;
    if(state === "COMPLETED" && (!exam.exam_date || exam.date_needs_review)) { setMessage("OMR 날짜를 확인하고 시험 날짜를 직접 입력하세요."); return; }
    setBusy(true);
    try {
      const result = await send(
        id ? "/exams/" + id : "/exams",
        { ...exam, exam_date: exam.exam_date || null, state },
        id ? "PUT" : "POST",
      );
      localStorage.removeItem(key);
      setExam(result);
      setMessage(result.warning || "시험 기록을 저장했습니다.");
      if (!id) go("exam/" + result.id);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  async function upload(files: FileList | null) {
    if (!files || !exam) return;
    setBusy(true);
    let next = structuredClone(exam);
    const warnings: string[] = [];
    const recognizedDates: (string|null)[] = [];
    try {
      for (const file of Array.from(files)) {
        const result = await analyzeUpload(file, setMessage);
        next.file_ids = [...new Set([...next.file_ids, ...result.file_ids])];
        for (const page of result.pages) {
          if (page.error) {
            warnings.push(`${file.name} ${page.page}페이지: ${page.error}`);
            continue;
          }
          const existing = next.subjects.find(
            (s: Any) => s.subject === page.subject,
          );
          if (
            existing &&
            !window.confirm(
              `${labels[page.subject]} 답안을 새 분석 결과로 바꿀까요? 기존 정/오답 체크와 메모는 유지됩니다.`,
            )
          )
            continue;
          const s = existing || blankSubject(page.subject);
          s.questions = s.questions.map((q: Any) => ({
            ...q,
            user_answer: String(page.answers[String(q.number)].answer),
            confidence: page.answers[String(q.number)].confidence,
            crop_file_id: page.answers[String(q.number)].crop_file_id,
            recognition: page.answers[String(q.number)],
          }));
          if (!existing) next.subjects.push(s);
          recognizedDates.push(page.date_details.iso || null);
          next.date_recognition = page.date;
          if(!page.date_details.iso) warnings.push("날짜 판독 오류: 시험 날짜를 직접 입력해주세요.");
          setActive(page.subject);
          setPreview(page);
        }
      }
      if(recognizedDates.length) Object.assign(next, applyRecognizedDates(recognizedDates));
      setExam(next);
      setMessage(
        warnings.join("\n") ||
          "분석 완료. 강조된 문항과 날짜를 확인한 뒤 저장하세요.",
      );
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  }
  if (!exam) return <div className="loading">시험을 불러오는 중…</div>;
  const subject = exam.subjects.find((s: Any) => s.subject === active),
    question = subject?.questions.find((q: Any) => q.number === selected);
  const summary = gradingSummary(subject?.questions || [], active);
  const needs = (q: Any) =>
    ["?", "MULTI", "UNKNOWN"].includes(q.user_answer) || q.confidence < 0.7;
  const count = exam.subjects.reduce(
    (sum: number, s: Any) => sum + s.questions.filter(needs).length,
    0,
  );
  return (
    <>
      <Heading
        eyebrow={id ? "EXAM DETAIL" : "NEW EXAM"}
        title={id ? exam.name || "시험 상세" : "새로운 시험을 기록하세요"}
        description="OMR 업로드 → 정/오답 체크 → 오답 배점 입력 → 저장"
        action={
          <div className="actions">
            <button disabled={busy} onClick={() => save("DRAFT")}>
              임시 저장
            </button>
            <button
              className="primary"
              disabled={busy}
              onClick={() => {
                if (
                  count &&
                  !confirm(
                    `확인 필요 ${count}문항이 있습니다. 그대로 저장할까요?`,
                  )
                )
                  return;
                save("COMPLETED");
              }}
            >
              기록 저장
            </button>
          </div>
        }
      />
      {message && (
        <div className="notice" role="status">
          {message}
        </div>
      )}
      <section className="panel">
        <h2>시험 정보</h2>
        <div className="form-grid">
          <Field label="시험 이름">
            <input
              required
              placeholder="예: 이해원 모의고사 시즌2"
              value={exam.name}
              onChange={(e) => change("name", e.target.value)}
            />
          </Field>
          <Field label="회차">
            <input
              placeholder="예: 3회"
              value={exam.round}
              onChange={(e) => change("round", e.target.value)}
            />
          </Field>
          <Field label="시험 날짜">
            <input
              type="date"
              value={exam.exam_date}
              onChange={(e) => setExam({...exam, exam_date:e.target.value, date_needs_review:!e.target.value})}
            />
          </Field>
          <Field label="시험 종류">
            <input
              list="exam-types"
              value={exam.exam_type}
              onChange={(e) => change("exam_type", e.target.value)}
            />
            <datalist id="exam-types">
              {kinds.map((k) => (
                <option key={k}>{k}</option>
              ))}
            </datalist>
          </Field>
        </div>
        {exam.date_needs_review && <div className="error" role="alert">OMR 날짜 {exam.date_recognition || '확인 불가'}를 확정하지 못했습니다. 위 시험 날짜를 직접 입력하세요. 답안 분석 결과는 유지됩니다.</div>}
        {!exam.date_needs_review && exam.date_recognition && <p className="muted">OMR 판독 날짜: {exam.date_recognition} · 필요하면 위 날짜를 수정하세요.</p>}
        <Field label="시험 총평 / 다음 시험 전략">
          <textarea
            rows={2}
            value={exam.memo}
            onChange={(e) => change("memo", e.target.value)}
            placeholder="시간 배분, 어려웠던 부분, 다음 시험의 목표를 기록하세요."
          />
        </Field>
        <small className="muted">
          수정 내용은 이 브라우저에 자동 보관됩니다. ‘기록 저장’으로 서버에
          저장하세요.
        </small>
      </section>
      <section className="upload-panel">
        <div>
          <span className="upload-icon">↥</span>
          <h2>
            {busy
              ? "OMR을 처리하고 있어요…"
              : "답안지를 올리면, 기록이 시작됩니다"}
          </h2>
          <p>국어 · 수학 · 영어 자동 구분 / PDF, JPG, PNG / 파일당 30MB</p>
        </div>
        <label className={"button primary " + (busy ? "disabled" : "")}>
          OMR 업로드
          <input
            type="file"
            hidden
            multiple
            accept=".pdf,.png,.jpg,.jpeg"
            disabled={busy}
            onChange={(e) => {
              upload(e.target.files);
              e.target.value = "";
            }}
          />
        </label>
      </section>
      <section className="panel">
        <div className="section-title">
          <div className="tabs">
            {Object.keys(labels).map((s) => (
              <button
                key={s}
                className={active === s ? "selected" : ""}
                onClick={() => {
                  setActive(s);
                  setSelected(null);
                }}
              >
                {labels[s]}{" "}
                {exam.subjects.some((x: Any) => x.subject === s) ? "●" : "○"}
              </button>
            ))}
          </div>
          <div className="actions">
            <label>
              <input
                type="checkbox"
                checked={onlyWrong}
                onChange={(e) => setOnlyWrong(e.target.checked)}
              />{" "}
              오답만
            </label>
            <label>
              <input
                type="checkbox"
                checked={onlyReview}
                onChange={(e) => setOnlyReview(e.target.checked)}
              />{" "}
              확인 필요 {count}
            </label>
          </div>
        </div>
        {!subject ? (
          <Empty>
            <button
              onClick={() =>
                change("subjects", [...exam.subjects, blankSubject(active)])
              }
            >
              {labels[active]} 직접 입력 시작
            </button>
          </Empty>
        ) : (
          <>
            <div className="legend">
              <span className="dot green" />
              정답 <span className="dot red" />
              오답 <span className="dot amber" />
              확인 필요 <span className="dot gray" />
              미응답·미채점
            </div>
            <div className="grading-toolbar">
              <div className="actions"><button onClick={()=>gradeAll('CORRECT')}>{labels[active]} 모두 정답</button><button onClick={()=>gradeAll('WRONG')}>{labels[active]} 모두 오답</button><button onClick={()=>gradeAll(null)}>체크 초기화</button></div>
              <p className="muted">전체를 정답으로 체크한 뒤 틀린 문항만 오답으로 바꾸세요. 배점은 오답에만 입력합니다.</p>
            </div>
            <div className="question-grid manual-grid">
              {subject.questions.filter((q:Any)=>(!onlyWrong||outcome(q)==='WRONG')&&(!onlyReview||needs(q))).map((q:Any)=>(
                <div className={'question-tile '+outcome(q)+(selected===q.number?' chosen':'')} key={q.number}>
                  <button className="question-open" onClick={()=>setSelected(q.number)} aria-label={`${q.number}번 답안 수정`}><span>{q.number}번</span><strong>{q.user_answer==='BLANK'?'—':q.user_answer}</strong></button>
                  <div className="grade-checks"><label><input type="checkbox" aria-label={`${q.number}번 정답`} checked={outcome(q)==='CORRECT'} onChange={e=>grade(q.number,e.target.checked?'CORRECT':null)}/>정답</label><label><input type="checkbox" aria-label={`${q.number}번 오답`} checked={outcome(q)==='WRONG'} onChange={e=>grade(q.number,e.target.checked?'WRONG':null)}/>오답</label></div>
                  {outcome(q)==='WRONG'&&<label className="wrong-points">배점<input type="number" aria-label={`${q.number}번 오답 배점`} min="0" max="100" step="0.5" placeholder="입력" value={q.score_value??''} onChange={e=>editQuestion(q.number,'score_value',e.target.value===''?null:Number(e.target.value))}/></label>}
                  {needs(q)&&<small className="recognition-warning">인식 확인 필요</small>}
                </div>
              ))}
            </div>
            {question && (
              <div className="question-editor">
                <div>
                  <h3>
                    {labels[active]} {question.number}번{" "}
                    <span className="badge">
                      {numeric(active, question.number) ? "단답형" : "객관식"}
                    </span>
                  </h3>
                  <div className="form-grid">
                    <Field label="내 답안">
                      {numeric(active, question.number) ? (
                        <input
                          value={question.user_answer}
                          onChange={(e) =>
                            editQuestion(
                              question.number,
                              "user_answer",
                              e.target.value,
                            )
                          }
                        />
                      ) : (
                        <select
                          value={question.user_answer}
                          onChange={(e) =>
                            editQuestion(
                              question.number,
                              "user_answer",
                              e.target.value,
                            )
                          }
                        >
                          {["1", "2", "3", "4", "5", "BLANK", "MULTI", "?"].map(
                            (v) => (
                              <option key={v}>{v}</option>
                            ),
                          )}
                        </select>
                      )}
                    </Field>
                    <Field label="영역">
                      <input
                        placeholder="예: 미적분"
                        value={question.category}
                        onChange={(e) =>
                          editQuestion(
                            question.number,
                            "category",
                            e.target.value,
                          )
                        }
                      />
                    </Field>
                  </div>
                  <p className="muted">
                    판독 신뢰도 {(question.confidence * 100).toFixed(0)}% ·{" "}
                    {states[outcome(question)]}
                  </p>
                  <details>
                    <summary>판독 점수 자세히</summary>
                    <pre>{JSON.stringify(question.recognition, null, 2)}</pre>
                  </details>
                </div>
                {question.crop_file_id && (
                  <img
                    className="crop"
                    alt={`${question.number}번 실제 OMR 마킹`}
                    src={"/api/files/" + question.crop_file_id}
                  />
                )}
              </div>
            )}
            <div className="score-box">
              <h3>{labels[active]} 성적</h3>
              <p>정답 {summary.correct} · 오답 {summary.wrong} · 미체크 {summary.ungraded}문항</p>
              <p className="computed-score">{summary.score == null ? '채점 중' : `${summary.score}점`} <small>100 − 오답 배점 {summary.deduction}점</small></p>
              {summary.missing.length>0 && <p className="notice">오답 배점 입력 필요: {summary.missing.join(', ')}번</p>}
              {summary.invalid && <p className="error">오답 배점 합계는 0~100점이어야 합니다.</p>}
              <div className="form-grid">
                {[
                  ["standard_score", "표준점수"],
                  ["percentile", "백분위"],
                  ["grade", "등급"],
                  ["duration", "풀이 시간 (분)"],
                  ["first_pass", "1바퀴 (분)"],
                ].map(([k, l]) => (
                  <Field key={k} label={l}>
                    <input
                      type="number"
                      min="0"
                      value={subject[k] ?? ""}
                      onChange={(e) =>
                        changeSubject(
                          k,
                          e.target.value === "" ? null : Number(e.target.value),
                        )
                      }
                    />
                  </Field>
                ))}
              </div>
            </div>
          </>
        )}
      </section>
      {preview && (
        <section className="panel">
          <h2>OMR 분석 결과 확인 · {labels[preview.subject]}</h2>
          <p>
            판독 날짜 {preview.date} · 정렬 품질{" "}
            {(preview.alignment.quality * 100).toFixed(0)}%
          </p>
          <select value={stage} onChange={(e) => setStage(e.target.value)}>
            {[
              ["original", "원본"],
              ["warped", "원근 보정"],
              ["aligned", "템플릿 정렬"],
              ["threshold", "Threshold"],
              ["difference", "Difference"],
              ["roi_overlay", "ROI"],
              ["result_overlay", "최종 인식"],
            ].map(([k, v]) => (
              <option value={k} key={k}>
                {v}
              </option>
            ))}
          </select>
          <div className="image-scroll">
            {preview.files[stage] && (
              <img
                src={"/api/files/" + preview.files[stage]}
                alt={stage + " OMR"}
              />
            )}
          </div>
          <details>
            <summary>날짜 8자리별 0~9 점수</summary>
            <pre>{JSON.stringify(preview.date_details, null, 2)}</pre>
          </details>
        </section>
      )}
      {id && (
        <section className="panel">
          <h2>연결된 시험지 / 원본</h2>
          <div className="actions">
            {exam.files
              ?.filter((f: Any) => ["original", "attachment"].includes(f.kind))
              .map((f: Any) => (
                <a
                  target="_blank"
                  rel="noreferrer"
                  key={f.id}
                  href={"/api/files/" + f.id}
                >
                  {f.filename} ↗
                </a>
              ))}
            <label className="button">
              시험지 PDF / 이미지 첨부
              <input
                hidden
                type="file"
                accept=".pdf,.png,.jpg,.jpeg"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (!f) return;
                  try {
                    const result = await uploadAttachment(f, id!);
                    setExam({
                      ...exam,
                      files: [
                        ...(exam.files || []),
                        { ...result, kind: "attachment" },
                      ],
                      file_ids: [...exam.file_ids, result.id],
                    });
                  } catch (e) {
                    fail(e);
                  }
                }}
              />
            </label>
            <button
              className="danger"
              onClick={async () => {
                if (
                  confirm(
                    "정말 삭제하시겠습니까? 관련 답안과 첨부파일도 삭제됩니다.",
                  )
                )
                  try {
                    await api("/exams/" + id, { method: "DELETE" });
                    localStorage.removeItem(key);
                    go("exams");
                  } catch (e) {
                    fail(e);
                  }
              }}
            >
              시험 삭제
            </button>
          </div>
        </section>
      )}
    </>
  );
}
function Wrong({ retry, fail }: any) {
  const [data, setData] = useState<Any[]>([]),
    [exams, setExams] = useState<Any[]>([]),
    [subject, setSubject] = useState(""),
    [status, setStatus] = useState(""),
    [tag, setTag] = useState(""),
    [exam, setExam] = useState(""),
    [favorite, setFavorite] = useState(false),
    [from, setFrom] = useState(""),
    [to, setTo] = useState("");
  const load = () =>
    api(
      "/wrong-answers?" +
        new URLSearchParams({
          subject,
          status,
          tag,
          exam_id: exam,
          favorite: String(favorite),
          retry: String(retry),
          date_from: from,
          date_to: to,
        }),
    )
      .then(setData)
      .catch(fail);
  useEffect(() => {
    load();
  }, [subject, status, tag, exam, favorite, from, to]);
  useEffect(() => {
    api("/exams").then(setExams).catch(fail);
  }, []);
  async function patch(q: Any, values: Any) {
    try {
      await send("/wrong-answers/" + q.id, values, "PATCH");
      load();
    } catch (e) {
      fail(e);
    }
  }
  return (
    <>
      <Heading
        eyebrow={retry ? "REVIEW QUEUE" : "WRONG ANSWER NOTE"}
        title={retry ? "다시 풀기" : "오답 한눈 보기"}
        description={
          retry
            ? "미복습, 다시 볼 문제, 중요 문제를 모았습니다."
            : "틀린 이유를 기록하고, 같은 실수를 줄여보세요."
        }
      />
      <div className="filters">
        <SubjectSelect value={subject} onChange={setSubject} />
        <select value={exam} onChange={(e) => setExam(e.target.value)}>
          <option value="">전체 시험</option>
          {exams.map((e) => (
            <option key={e.id} value={e.id}>
              {e.name} {e.round}
            </option>
          ))}
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="">전체 복습 상태</option>
          {reviews.map((v) => (
            <option key={v}>{v}</option>
          ))}
        </select>
        <input
          list="tags"
          placeholder="태그 검색"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
        />
        <datalist id="tags">
          {tags.map((t) => (
            <option key={t}>{t}</option>
          ))}
        </datalist>
        <label>
          <input
            type="checkbox"
            checked={favorite}
            onChange={(e) => setFavorite(e.target.checked)}
          />{" "}
          중요 문제만
        </label>
        <input
          aria-label="시작일"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
        <input
          aria-label="종료일"
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      </div>
      <p className="muted">총 {data.length}문항</p>
      <div className="wrong-grid">
        {data.map((q) => (
          <article className="wrong-card" key={q.id}>
            <div className="section-title">
              <span className="badge">{labels[q.subject]}</span>
              <button
                className="star"
                aria-label="중요 문제"
                onClick={() => patch(q, { favorite: !q.favorite })}
              >
                {q.favorite ? "★" : "☆"}
              </button>
            </div>
            <h2>
              {q.number}번 <small>{states[q.outcome]}</small>
            </h2>
            <p>
              {q.exam_name} {q.round}
            </p>
            <small className="muted">{q.exam_date}</small>
            <div className="answer-pair">
              <span>
                내 답 <b>{q.user_answer}</b>
              </span>
              <span>
                채점 <b>{states[q.outcome]}</b>
              </span>
              <small>{q.score_value ?? "—"}점</small>
            </div>
            <div>
              {q.tags.map((t: string) => (
                <span className="badge" key={t}>
                  {t}
                </span>
              ))}
            </div>
            <p className="note-preview">{q.note || "아직 메모가 없어요."}</p>
            <div className="actions">
              <select
                value={q.review_status}
                onChange={(e) => patch(q, { review_status: e.target.value })}
              >
                {reviews.map((r) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
              <button onClick={() => go("wrong/" + q.id)}>상세</button>
              <button onClick={() => patch(q, { review_status: "해결" })}>
                해결 ✓
              </button>
            </div>
          </article>
        ))}
      </div>
      {!data.length && <Empty>조건에 맞는 오답이 없어요</Empty>}
    </>
  );
}
function WrongDetail({ id, fail }: any) {
  const [q, setQ] = useState<Any | null>(null),
    [message, setMessage] = useState("");
  useEffect(() => {
    api("/wrong-answers/" + id)
      .then(setQ)
      .catch(fail);
  }, [id]);
  if (!q) return <div className="loading">문항을 불러오는 중…</div>;
  const set = (k: string, v: any) => setQ({ ...q, [k]: v });
  return (
    <>
      <Heading
        eyebrow="REVIEW DETAIL"
        title={`${labels[q.subject] || ""} ${q.number}번 오답 기록`}
        description="실수 원인과 다음에 주의할 점을 남겨보세요."
        action={<button onClick={() => go("wrong")}>← 목록</button>}
      />
      <section className="panel">
        <p>
          <a href={"#exam/" + q.exam_id}>
            {q.exam_name} {q.round} → 시험 상세
          </a>
        </p>
        <div className="actions">
          {q.attachments?.map((f: Any) => (
            <a
              className="button"
              key={f.id}
              target="_blank"
              rel="noreferrer"
              href={"/api/files/" + f.id + "#page=" + (q.page || 1)}
            >
              {f.filename} · {q.page || 1}페이지 ↗
            </a>
          ))}
        </div>
        <div className="answer-pair">
          <span>
            내 답 <b>{q.user_answer}</b>
          </span>
          <span>
            채점 <b>{states[q.outcome]}</b>
          </span>
          <span>{states[q.outcome]}</span>
        </div>
        {q.crop_file_id && (
          <img
            className="crop"
            alt="실제 OMR 마킹"
            src={"/api/files/" + q.crop_file_id}
          />
        )}
        <div className="form-grid">
          <Field label="복습 상태">
            <select
              value={q.review_status}
              onChange={(e) => set("review_status", e.target.value)}
            >
              {reviews.map((r) => (
                <option key={r}>{r}</option>
              ))}
            </select>
          </Field>
          <Field label="영역">
            <input
              value={q.category}
              onChange={(e) => set("category", e.target.value)}
            />
          </Field>
          <Field label="시험지 페이지">
            <input
              type="number"
              min="1"
              value={q.page ?? ""}
              onChange={(e) =>
                set("page", e.target.value ? Number(e.target.value) : null)
              }
            />
          </Field>
          <Field label="중요 문제">
            <input
              type="checkbox"
              checked={q.favorite}
              onChange={(e) => set("favorite", e.target.checked)}
            />
          </Field>
        </div>
        <Field label="태그 (쉼표로 구분)">
          <input
            list="review-tags"
            value={q.tags.join(", ")}
            onChange={(e) =>
              set(
                "tags",
                e.target.value.split(",").map((v) => v.trim()),
              )
            }
          />
          <datalist id="review-tags">
            {tags.map((t) => (
              <option key={t}>{t}</option>
            ))}
          </datalist>
        </Field>
        <div className="tag-picks">
          {tags.map((t) => (
            <button
              key={t}
              onClick={() =>
                set("tags", [...new Set([...q.tags.filter(Boolean), t])])
              }
            >
              ＋{t}
            </button>
          ))}
        </div>
        <Field label="실수 원인 / 풀이 메모 / 다음에 주의">
          <textarea
            rows={8}
            value={q.note}
            onChange={(e) => set("note", e.target.value)}
          />
        </Field>
        <button
          className="primary"
          onClick={async () => {
            try {
              await send(
                "/wrong-answers/" + id,
                { ...q, tags: q.tags.filter(Boolean) },
                "PATCH",
              );
              setMessage("복습 기록을 저장했습니다.");
            } catch (e) {
              fail(e);
            }
          }}
        >
          복습 기록 저장
        </button>
        {message && <p className="notice">{message}</p>}
      </section>
    </>
  );
}
function Stats({ fail }: any) {
  const [subject, setSubject] = useState("math"),
    [kind, setKind] = useState(""),
    [metric, setMetric] = useState("display_score"),
    [data, setData] = useState<Any | null>(null);
  useEffect(() => {
    api("/stats?" + new URLSearchParams({ subject, exam_type: kind }))
      .then(setData)
      .catch(fail);
  }, [subject, kind]);
  return (
    <>
      <Heading
        eyebrow="STUDY INSIGHTS"
        title="기록으로 보는 나의 변화"
        description="점수의 흐름과 오답 분포를 함께 살펴보세요."
      />
      <div className="filters">
        <SubjectSelect all={false} value={subject} onChange={setSubject} />
        <select value={metric} onChange={(e) => setMetric(e.target.value)}>
          {[
            ["display_score", "원점수"],
            ["standard_score", "표준점수"],
            ["percentile", "백분위"],
            ["grade", "등급"],
            ["accuracy", "정답률"],
          ].map(([k, v]) => (
            <option key={k} value={k}>
              {v}
            </option>
          ))}
        </select>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">전체 시험 종류</option>
          {kinds.map((k) => (
            <option key={k}>{k}</option>
          ))}
        </select>
      </div>
      {data && (
        <>
          <div className="summary-grid">
            {[
              ["최근 5회 평균", data.average5],
              ["최근 10회 평균", data.average10],
              ["최고 / 최저", `${data.max ?? "—"} / ${data.min ?? "—"}`],
              ["시험 횟수", data.count],
            ].map(([k, v]) => (
              <div className="metric" key={k}>
                <span>{k}</span>
                <strong>{v ?? "—"}</strong>
              </div>
            ))}
          </div>
          <section className="panel">
            <h2>{labels[subject]} 성적 추이</h2>
            {data.series.length ? (
              <ResponsiveContainer width="100%" height={310}>
                <LineChart data={data.series}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="date" />
                  <YAxis
                    reversed={metric === "grade"}
                    domain={metric === "grade" ? [1, 9] : ["auto", "auto"]}
                  />
                  <Tooltip />
                  <Line
                    type="linear"
                    dataKey={metric}
                    name={
                      metric === "display_score"
                        ? "원점수"
                        : metric === "accuracy"
                          ? "정답률"
                          : metric === "grade"
                            ? "등급"
                            : metric === "percentile"
                              ? "백분위"
                              : "표준점수"
                    }
                    stroke="#247361"
                    strokeWidth={3}
                    connectNulls={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            ) : (
              <Empty>그래프를 그릴 시험 기록이 없어요</Empty>
            )}
            <p className="muted">
              점수 미입력 시험은 그래프에서 비워 둡니다. 평균은 점수가 있는 시험
              기준입니다.
            </p>
          </section>
          <div className="dashboard-columns">
            <section className="panel">
              <h2>답안 상태 분포</h2>
              {Object.entries(data.counts).map(([k, v]) => (
                <div className="stat-row" key={k}>
                  <span>{states[k]}</span>
                  <b>{String(v)}문항</b>
                </div>
              ))}
              <p>미복습 오답 {data.unreviewed}문항</p>
            </section>
            <section className="panel">
              <h2>영역별 정답률 / 오답</h2>
              {Object.entries(data.categories).map(([k, v]: any) => (
                <div className="stat-row" key={k}>
                  <span>{k}</span>
                  <b>
                    {((v.correct / v.total) * 100).toFixed(1)}% · 오답 {v.wrong}
                    /{v.total}
                  </b>
                </div>
              ))}
            </section>
          </div>
          <section className="panel">
            <h2>최근 10회 문항 번호별 오답</h2>
            <p className="muted">
              문항 번호가 같아도 같은 개념을 의미하지 않습니다. 정답/오답을 체크한
              문항 기준입니다.
            </p>
            <div className="repeat-grid">
              {Object.entries(data.repeated).map(([n, v]: any) => (
                <div key={n}>
                  <span>{n}번</span>
                  <b>
                    {v.wrong} / {v.total}
                  </b>
                  <meter min={0} max={v.total} value={v.wrong} />
                </div>
              ))}
            </div>
          </section>
        </>
      )}
    </>
  );
}
function Settings({ user, setUser, fail }: any) {
  const [name, setName] = useState(user.username),
    [old, setOld] = useState(""),
    [password, setPassword] = useState(""),
    [message, setMessage] = useState("");
  return (
    <>
      <Heading
        eyebrow="PREFERENCES"
        title="설정"
        description="계정과 소중한 학습 기록을 관리하세요."
      />
      <section className="panel narrow">
        <h2>내 계정</h2>
        <Field label="닉네임">
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="현재 비밀번호">
          <input
            type="password"
            value={old}
            onChange={(e) => setOld(e.target.value)}
          />
        </Field>
        <Field label="새 비밀번호 (변경할 때만)">
          <input
            type="password"
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </Field>
        <button
          className="primary"
          onClick={async () => {
            try {
              setUser(
                await send(
                  "/auth/me",
                  { username: name, old_password: old, password },
                  "PATCH",
                ),
              );
              setOld("");
              setPassword("");
              setMessage("계정 정보를 변경했습니다.");
            } catch (e) {
              fail(e);
            }
          }}
        >
          변경 저장
        </button>
      </section>
      <section className="panel">
        <h2>데이터 백업 및 복구</h2>
        <p className="muted">
          JSON은 답안·점수·메모·태그와 연결된 OMR/시험지 파일을 함께 보관합니다.
          이미지가 많으면 파일이 커집니다. 같은 백업은 중복 기록을 건너뜁니다.
        </p>
        <div className="actions">
          <button
            onClick={() =>
              exportBackup()
                .then((d) => download(d, "omr-backup.json"))
                .catch(fail)
            }
          >
            JSON 백업
          </button>
          <a className="button" href="/api/export?format=csv">
            전체 CSV
          </a>
          <a className="button" href="/api/export?format=csv&subject=math">
            수학 CSV
          </a>
          <a className="button" href="/api/export?format=csv&wrong_only=true">
            오답 CSV
          </a>
          <label className="button">
            JSON 복구
            <input
              type="file"
              hidden
              accept=".json"
              onChange={async (e) => {
                const f = e.target.files?.[0];
                if (!f) return;
                try {
                  const r = await importBackup(f);
                  setMessage(`${r.added}개 복원, ${r.skipped}개 중복 건너뜀`);
                } catch (e) {
                  fail(e);
                }
                e.target.value = "";
              }}
            />
          </label>
        </div>
      </section>
      {message && <p className="notice">{message}</p>}
      <button
        className="danger"
        onClick={async () => {
          try {
            await send("/auth/logout", {});
            setUser(null);
          } catch (e) {
            fail(e);
          }
        }}
      >
        로그아웃
      </button>
    </>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
