"""Desktop UI and batch CLI. python main.py --help"""

import argparse, json, logging, threading, queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk
from omr import OMREngine
from omr.io import ROOT, load_pages, export_results
from omr.student_number import validate_date

LABELS = {"korean": "국어", "math": "수학", "english": "영어"}
STAGES = {
    "원본": "original",
    "원근 보정": "warped",
    "템플릿 정렬": "aligned",
    "Threshold": "threshold",
    "Difference": "difference",
    "ROI": "roi_overlay",
    "최종 인식": "result_overlay",
}


class Desktop:
    def __init__(self, root, debug=False):
        self.root = root
        self.debug = debug
        self.paths = []
        self.results = []
        self.folders = []
        self.index = 0
        self.events = queue.Queue()
        root.title("OMR Study · 답안 자동 인식")
        root.geometry("1380x900")
        bar = ttk.Frame(root, padding=10)
        bar.pack(fill="x")
        for title, command in [
            ("파일 선택", self.choose),
            ("OMR 분석", self.analyze),
            ("결과 확인", self.show_results),
            ("결과 수정", self.edit),
            ("CSV 저장", lambda: self.save("csv")),
            ("JSON 저장", lambda: self.save("json")),
        ]:
            ttk.Button(bar, text=title, command=command).pack(side="left", padx=4)
        ttk.Button(bar, text="좌표 보정", command=self.calibrate).pack(side="right")
        self.status = tk.StringVar(value="PDF 또는 JPG/PNG 파일을 선택하세요.")
        ttk.Label(root, textvariable=self.status, padding=8).pack(fill="x")
        controls = ttk.Frame(root, padding=8)
        controls.pack(fill="x")
        self.page = ttk.Combobox(controls, state="readonly", width=32)
        self.page.pack(side="left")
        self.page.bind("<<ComboboxSelected>>", self.select_page)
        self.stage = ttk.Combobox(
            controls, values=list(STAGES), state="readonly", width=18
        )
        self.stage.set("최종 인식")
        self.stage.pack(side="left", padx=8)
        self.stage.bind("<<ComboboxSelected>>", lambda e: self.show_image())
        ttk.Label(controls, text="날짜").pack(side="left")
        self.date = tk.StringVar()
        ttk.Entry(controls, textvariable=self.date, width=16).pack(side="left", padx=5)
        ttk.Button(controls, text="날짜 수정 적용", command=self.edit_date).pack(
            side="left"
        )
        body = ttk.Panedwindow(root, orient="horizontal")
        body.pack(fill="both", expand=True)
        left = ttk.Frame(body)
        body.add(left, weight=3)
        self.canvas = tk.Canvas(left, bg="#edf1e9")
        self.canvas.pack(fill="both", expand=True)
        right = ttk.Frame(body, padding=10)
        body.add(right, weight=2)
        self.tree = ttk.Treeview(
            right,
            columns=("q", "answer", "status", "confidence"),
            show="headings",
            height=20,
        )
        for name, title, width in [
            ("q", "문항", 65),
            ("answer", "답안", 90),
            ("status", "상태", 95),
            ("confidence", "신뢰도", 80),
        ]:
            self.tree.heading(name, text=title)
            self.tree.column(name, width=width, anchor="center")
        self.tree.tag_configure("review", background="#fff0c2")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", self.inspect)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        self.crop = ttk.Label(right)
        self.crop.pack(fill="x", pady=8)
        self.details = tk.Text(right, height=9, wrap="word")
        self.details.pack(fill="x")
        ttk.Button(right, text="날짜 자리별 점수 보기", command=self.date_scores).pack(
            fill="x"
        )
        self.root.after(100, self.poll)

    def choose(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("OMR 파일", "*.pdf *.jpg *.jpeg *.png")]
        )
        if not paths:
            return
        self.paths = list(paths)
        self.status.set(f"{len(paths)}개 파일 선택됨")
        try:
            import cv2

            image = next(load_pages(paths[0]))
            self.render(Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB)))
        except Exception as e:
            messagebox.showerror("파일 오류", str(e))

    def render(self, image):
        self.root.update_idletasks()
        image.thumbnail(
            (max(600, self.canvas.winfo_width()), max(450, self.canvas.winfo_height()))
        )
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(5, 5, anchor="nw", image=self.photo)

    def analyze(self):
        if not self.paths:
            return messagebox.showinfo("파일 선택", "먼저 파일을 선택하세요.")
        if getattr(self, "running", False):
            return
        self.running = True
        self.status.set("과목 판별 → 원근 보정 → 정렬 → 답안 판독 중…")
        paths = list(self.paths)

        def worker():
            try:
                from uuid import uuid4

                engine = OMREngine()
                results = []
                folders = []
                for path in paths:
                    directory = ROOT / "output/debug" / str(uuid4())
                    pages = engine.analyze_file(path, directory)
                    for i, r in enumerate(pages):
                        results.append(r)
                        folders.append(directory / f"page_{i + 1}")
                self.events.put(("done", (results, folders)))
            except Exception as exc:
                self.events.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            kind, value = self.events.get_nowait()
            self.running = False
            if kind == "error":
                self.status.set(value)
                messagebox.showerror("분석 오류", value)
            else:
                self.results, self.folders = value
                self.index = 0
                self.page["values"] = [
                    f"{i + 1}. {LABELS.get(r.get('subject'), '인식 실패')}"
                    for i, r in enumerate(self.results)
                ]
                if self.results:
                    self.page.current(0)
                    self.show_results()
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def select_page(self, event=None):
        self.index = self.page.current()
        self.show_results()

    def show_results(self):
        if not self.results:
            return
        r = self.results[self.index]
        self.tree.delete(*self.tree.get_children())
        if "error" in r:
            self.status.set(r["error"])
            self.date.set("")
            return
        self.date.set(r["date"])
        self.status.set(
            f"{LABELS[r['subject']]} · {len(r['answers'])}문항 · 정렬 {r['alignment']['quality']:.1%} · 확인 필요 {len(r['review_questions'])}문항"
        )
        for q, a in r["answers"].items():
            self.tree.insert(
                "",
                "end",
                iid=q,
                values=(q, a["answer"], a["status"], f"{a['confidence']:.1%}"),
                tags=("review",) if q in r["review_questions"] else (),
            )
        self.show_image()

    def show_image(self):
        if not self.folders:
            return
        path = self.folders[self.index] / (STAGES[self.stage.get()] + ".png")
        if path.exists():
            with Image.open(path) as im:
                self.render(im.copy())

    def inspect(self, event=None):
        selection = self.tree.selection()
        if not selection:
            return
        q = selection[0]
        path = self.folders[self.index] / f"q{q}.png"
        if path.exists():
            with Image.open(path) as im:
                im.thumbnail((480, 230))
                self.crop_photo = ImageTk.PhotoImage(im.copy())
                self.crop.configure(image=self.crop_photo)
        self.details.delete("1.0", "end")
        self.details.insert(
            "end",
            json.dumps(
                self.results[self.index]["answers"][q], ensure_ascii=False, indent=2
            ),
        )

    def date_scores(self):
        if not self.results or "error" in self.results[self.index]:
            return
        window = tk.Toplevel(self.root)
        window.title("수험번호 가상 위치 0~9 점수")
        text = tk.Text(window, width=70, height=35)
        text.pack(fill="both", expand=True)
        text.insert(
            "end",
            json.dumps(
                self.results[self.index]["date_details"], ensure_ascii=False, indent=2
            ),
        )

    def edit(self):
        selected = self.tree.selection()
        if not selected:
            return messagebox.showinfo("문항 선택", "수정할 문항을 선택하세요.")
        q = selected[0]
        r = self.results[self.index]
        numeric = r["subject"] == "math" and (16 <= int(q) <= 22 or int(q) >= 29)
        dialog = tk.Toplevel(self.root)
        dialog.title(f"{q}번 답안 수정")
        dialog.transient(self.root)
        value = tk.StringVar(value=str(r["answers"][q]["answer"]))
        field = (
            ttk.Entry(dialog, textvariable=value)
            if numeric
            else ttk.Combobox(
                dialog,
                textvariable=value,
                values=["1", "2", "3", "4", "5", "BLANK", "MULTI", "?"],
                state="readonly",
            )
        )
        field.pack(padx=30, pady=20)

        def apply():
            answer = value.get().strip()
            if answer not in ("BLANK", "MULTI", "?"):
                if not answer.isdigit() or not (
                    0 <= int(answer) <= 999 if numeric else 1 <= int(answer) <= 5
                ):
                    return messagebox.showerror(
                        "입력 오류", "허용되는 답안을 입력하세요."
                    )
                answer = int(answer)
            old = r["answers"][q]
            old.setdefault("original_recognition", dict(old))
            old.update(
                answer=answer,
                confidence=1.0,
                status="OK"
                if isinstance(answer, int)
                else "UNKNOWN"
                if answer == "?"
                else answer,
                manually_reviewed=True,
            )
            r["review_questions"] = [
                n
                for n, a in r["answers"].items()
                if a["status"] in ("UNKNOWN", "MULTI") or a["confidence"] < 0.7
            ]
            dialog.destroy()
            self.show_results()

        ttk.Button(dialog, text="적용", command=apply).pack(pady=10)

    def edit_date(self):
        if not self.results or "error" in self.results[self.index]:
            return
        raw = self.date.get().replace("-", "")
        iso, warning = validate_date(raw)
        if len(raw) != 8:
            return messagebox.showerror(
                "날짜 오류", "YYYYMMDD 또는 YYYY-MMDD 형식으로 입력하세요."
            )
        r = self.results[self.index]
        r["date"] = raw[:4] + "-" + raw[4:]
        r["date_details"].update(
            raw=raw, display=r["date"], iso=iso, warning=warning, manually_reviewed=True
        )
        if warning:
            messagebox.showwarning("날짜 확인", warning)

    def save(self, extension):
        if not self.results:
            return
        filename = filedialog.asksaveasfilename(
            defaultextension="." + extension,
            filetypes=[(extension.upper(), "*." + extension)],
        )
        if filename:
            export_results(self.results, filename)
            self.status.set("저장됨: " + filename)

    def calibrate(self):
        from calibration.calibration_gui import CalibrationGUI

        CalibrationGUI(tk.Toplevel(self.root))


def main():
    parser = argparse.ArgumentParser(description="OMR Study 데스크톱 / 배치 분석")
    parser.add_argument("files", nargs="*")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--output", default=str(ROOT / "output/results.json"))
    args = parser.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.debug else logging.INFO)
    if args.files:
        engine = OMREngine()
        results = []
        for i, path in enumerate(args.files):
            results.extend(
                engine.analyze_file(
                    path,
                    ROOT / "output/debug" / f"file_{i + 1}" if args.debug else None,
                )
            )
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        export_results(results, args.output)
        print(args.output)
    else:
        root = tk.Tk()
        Desktop(root, args.debug)
        root.mainloop()


if __name__ == "__main__":
    main()
