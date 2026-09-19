type RecordData = Record<string, any>;

async function request(path: string, body?: unknown): Promise<any> {
  const response = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    credentials: "same-origin",
    headers: body instanceof FormData ? {} : { "Content-Type": "application/json" },
    body: body instanceof FormData ? body : body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({ detail: "서버 응답을 확인할 수 없습니다. 잠시 후 다시 시도하세요." }));
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail));
  return data;
}

async function directUpload(file: File, kind: string, exam_id?: string) {
  if (!file.size || file.size > 30 * 1024 * 1024) throw new Error("파일은 0바이트보다 크고 30MB 이하여야 합니다.");
  const ticket = await request("/uploads/sign", { filename: file.name, size: file.size, kind, exam_id });
  const uploaded = await fetch(ticket.upload_url, {
    method: "PUT", body: file,
    headers: { "Content-Type": file.type || "application/octet-stream", "x-upsert": "false" },
    credentials: "omit",
  });
  if (!uploaded.ok) throw new Error("파일 업로드에 실패했습니다. 저장 공간이나 네트워크 상태를 확인하세요.");
  return request("/uploads/complete", { file_id: ticket.file_id });
}

export async function analyzeUpload(file: File, progress: (message: string) => void) {
  const config = await request("/config");
  if (!config.direct_upload) {
    const body = new FormData(); body.append("file", file);
    return request("/omr/analyze", body);
  }
  progress(`${file.name} 업로드 중…`);
  const uploaded = await directUpload(file, "original");
  const result: { pages: any[]; file_ids: string[] } = { pages: [], file_ids: [uploaded.id] };
  for (let page = 1; page <= uploaded.pages; page++) {
    progress(`${file.name} ${page}/${uploaded.pages}페이지 분석 중…`);
    const part = await request("/omr/analyze-page", { file_id: uploaded.id, page });
    result.pages.push(...part.pages);
    result.file_ids.push(...part.file_ids);
  }
  result.file_ids = [...new Set(result.file_ids)];
  return result;
}

export async function uploadAttachment(file: File, examId: string) {
  if ((await request("/config")).direct_upload) return directUpload(file, "attachment", examId);
  const body = new FormData(); body.append("file", file);
  return request(`/exams/${examId}/attachments`, body);
}

function base64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(",")[1]);
    reader.onerror = () => reject(new Error("백업 파일을 읽을 수 없습니다."));
    reader.readAsDataURL(blob);
  });
}

export async function exportBackup() {
  // Transfer files separately so backups do not cross the function response limit.
  const backup = await request("/export?manifest=true");
  for (const file of backup.files) {
    const response = await fetch(file.url, { credentials: "same-origin" });
    if (!response.ok) throw new Error("백업 이미지 다운로드에 실패했습니다.");
    file.data = await base64(await response.blob());
    delete file.url;
  }
  return backup;
}

export async function importBackup(file: File) {
  const backup = JSON.parse(await file.text());
  if (!(await request("/config")).direct_upload) return request("/import", backup);
  if (backup.version !== 1 || !Array.isArray(backup.exams) || backup.exams.length > 1000 || !Array.isArray(backup.files || [])) throw new Error("지원하지 않는 백업입니다.");
  let added = 0, skipped = 0;
  const existing = new Set<string>((await request("/exams")).map((exam: RecordData) => exam.id));
  for (const exam of backup.exams) {
    if (existing.has(exam.id)) { skipped++; continue; }
    // Ask the server before transferring files; restored UUIDs differ by account.
    if ((await request("/import/check", { original_id: exam.id })).exists) { skipped++; continue; }
    const files = [];
    for (const entry of (backup.files || []).filter((f: RecordData) => exam.file_ids.includes(f.id))) {
      const bytes = Uint8Array.from(atob(entry.data), c => c.charCodeAt(0));
      const name = "restore" + entry.extension;
      const uploaded = await directUpload(new File([bytes], name), "backup-asset");
      files.push({ id: entry.id, filename: entry.filename, kind: entry.kind, stored_file_id: uploaded.id });
    }
    const result = await request("/import", { version: 1, exams: [exam], files });
    added += result.added; skipped += result.skipped;
  }
  return { added, skipped };
}
