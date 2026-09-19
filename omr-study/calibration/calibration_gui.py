"""Visual normalized-coordinate editor; drag, Shift=row, Ctrl=column; wheel zoom."""

from pathlib import Path
import sys, json, copy

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from PIL import Image, ImageTk
from omr.io import ROOT


class CalibrationGUI:
    def __init__(self, root):
        self.root = root
        root.title("OMR 가상 좌표 보정")
        root.geometry("1300x900")
        self.path = ROOT / "config/templates.json"
        self.config = json.loads(self.path.read_text(encoding="utf-8"))
        self.zoom = 0.6
        self.selected = None
        self.undo = []
        bar = ttk.Frame(root, padding=8)
        bar.pack(fill="x")
        self.subject = ttk.Combobox(bar, values=list(self.config), state="readonly")
        self.subject.set("math")
        self.subject.pack(side="left")
        self.subject.bind("<<ComboboxSelected>>", lambda e: self.load())
        for name, command in [
            ("저장", self.save),
            ("좌표 추가", self.add),
            ("선택 삭제", self.delete),
            ("되돌리기", self.back),
            ("확대", lambda: self.scale(1.2)),
            ("축소", lambda: self.scale(1 / 1.2)),
        ]:
            ttk.Button(bar, text=name, command=command).pack(side="left", padx=4)
        ttk.Label(
            root,
            text="드래그: 좌표 이동 | Shift+드래그: 같은 행 | Ctrl+드래그: 같은 열 | 오른쪽 드래그: 화면 이동 | 휠: 확대/축소 | 주황색: 날짜 가상 위치",
        ).pack(fill="x", padx=10)
        frame = ttk.Frame(root)
        frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(frame, bg="#ddd")
        self.canvas.grid(row=0, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        for orient, row, col, command in [
            ("horizontal", 1, 0, self.canvas.xview),
            ("vertical", 0, 1, self.canvas.yview),
        ]:
            scroll = ttk.Scrollbar(frame, orient=orient, command=command)
            scroll.grid(
                row=row, column=col, sticky="ew" if orient == "horizontal" else "ns"
            )
            self.canvas.configure(
                **{
                    (
                        "xscrollcommand" if orient == "horizontal" else "yscrollcommand"
                    ): scroll.set
                }
            )
        self.status = tk.StringVar()
        ttk.Label(root, textvariable=self.status).pack(fill="x")
        self.canvas.bind("<Button-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: self.draw())
        self.canvas.bind(
            "<MouseWheel>", lambda e: self.scale(1.15 if e.delta > 0 else 1 / 1.15)
        )
        self.canvas.bind("<Button-3>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind(
            "<B3-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1)
        )
        self.load()

    def load(self):
        self.selected = None
        self.image = Image.open(
            ROOT / self.config[self.subject.get()]["template"]
        ).convert("RGB")
        self.draw()

    def points(self):
        c = self.config[self.subject.get()]
        for i, col in enumerate(c["student_number"]["columns"]):
            for d, p in col["digits"].items():
                yield f"D{i + 1}:{d}", col["digits"], d, p
        for q, spec in c["questions"].items():
            if spec["type"] == "choice":
                for a, p in spec["options"].items():
                    yield f"Q{q}:{a}", spec["options"], a, p
            else:
                for i, col in enumerate(spec["columns"]):
                    for d, p in col["digits"].items():
                        yield f"Q{q}.{i}:{d}", col["digits"], d, p

    def draw(self):
        w, h = self.image.size
        self.canvas.delete("all")
        self.photo = ImageTk.PhotoImage(
            self.image.resize((int(w * self.zoom), int(h * self.zoom)))
        )
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, w * self.zoom, h * self.zoom))
        for label, container, key, p in self.points():
            x, y = p[0] * w * self.zoom, p[1] * h * self.zoom
            r = 7 * self.zoom
            color = "#ff8500" if label.startswith("D") else "#007bc4"
            if self.selected and label == self.selected[0]:
                color = "#00aa22"
                r += 3
            self.canvas.create_oval(
                x - r, y - r * 1.5, x + r, y + r * 1.5, outline=color, width=2
            )
            if self.zoom > 0.9 or label.startswith("D"):
                self.canvas.create_text(
                    x + 8, y - 10, text=label, fill=color, font=("Arial", 8)
                )

    def scale(self, factor):
        self.zoom = max(0.25, min(3, self.zoom * factor))
        self.draw()

    def position(self, event):
        return [
            self.canvas.canvasx(event.x) / (self.image.width * self.zoom),
            self.canvas.canvasy(event.y) / (self.image.height * self.zoom),
        ]

    def press(self, event):
        p = self.position(event)
        points = list(self.points())
        if not points:
            return
        self.selected = min(
            points,
            key=lambda v: (
                ((v[3][0] - p[0]) * self.image.width) ** 2
                + ((v[3][1] - p[1]) * self.image.height) ** 2
            ),
        )
        self.undo.append(copy.deepcopy(self.config))
        self.start = p
        self.originals = [
            (label, container, key, point.copy())
            for label, container, key, point in points
        ]
        self.status.set(self.selected[0] + " " + str(self.selected[3]))
        self.draw()

    def drag(self, event):
        if not self.selected:
            return
        p = self.position(event)
        dx, dy = p[0] - self.start[0], p[1] - self.start[1]
        target = next(v[3] for v in self.originals if v[0] == self.selected[0])
        for label, container, key, origin in self.originals:
            chosen = label == self.selected[0]
            if event.state & 1:
                chosen = abs(origin[1] - target[1]) < 0.004
            if event.state & 4:
                chosen = abs(origin[0] - target[0]) < 0.004
            if chosen:
                container[key] = [
                    min(0.999, max(0.001, origin[0] + dx)),
                    min(0.999, max(0.001, origin[1] + dy)),
                ]
        self.draw()

    def add(self):
        name = simpledialog.askstring(
            "좌표 추가", "주소: D1:3 또는 Q1:2 또는 Q16.0:1 (숫자 열은 0부터)"
        )
        if not name:
            return
        try:
            target, key = name.split(":")
            c = self.config[self.subject.get()]
            if target.startswith("D"):
                container = c["student_number"]["columns"][int(target[1:]) - 1][
                    "digits"
                ]
            elif "." in target:
                q, col = target[1:].split(".")
                container = c["questions"][q]["columns"][int(col)]["digits"]
            else:
                container = c["questions"][target[1:]]["options"]
            if key in container:
                raise ValueError("이미 있는 좌표입니다. 드래그해서 이동하세요.")
            if not key.isdigit() or not 0 <= int(key) <= 9:
                raise ValueError("숫자 키를 확인하세요.")
            self.undo.append(copy.deepcopy(self.config))
            container[key] = [0.5, 0.5]
            self.draw()
        except (ValueError, KeyError, IndexError) as e:
            messagebox.showerror("좌표 오류", str(e))

    def delete(self):
        if not self.selected:
            return
        self.undo.append(copy.deepcopy(self.config))
        _, container, key, _ = self.selected
        container.pop(key, None)
        self.selected = None
        self.draw()

    def back(self):
        if self.undo:
            self.config = self.undo.pop()
            self.selected = None
            self.load()

    def save(self):
        for subject, c in self.config.items():
            if len(c["student_number"]["columns"]) != 8 or any(
                set(col["digits"]) != set(map(str, range(10)))
                for col in c["student_number"]["columns"]
            ):
                return messagebox.showerror(
                    "저장 오류",
                    subject
                    + ": 날짜 8열마다 0~9 좌표가 필요합니다. 삭제한 좌표를 복구하세요.",
                )
            for q, spec in c["questions"].items():
                if spec["type"] == "choice" and set(spec["options"]) != set("12345"):
                    return messagebox.showerror(
                        "저장 오류", f"{subject} {q}번: 보기 1~5가 필요합니다."
                    )
                if spec["type"] == "numeric" and any(
                    set(col["digits"]) != set("123456789" if i == 0 else "0123456789")
                    for i, col in enumerate(spec["columns"])
                ):
                    return messagebox.showerror(
                        "저장 오류", f"{subject} {q}번: 단답형 숫자 좌표가 빠졌습니다."
                    )
        backup = self.path.with_suffix(".backup.json")
        backup.write_text(self.path.read_text(encoding="utf-8"), encoding="utf-8")
        self.path.write_text(
            json.dumps(self.config, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.status.set("저장 완료. 데스크톱 재분석 / 웹 서버 재시작 후 적용됩니다.")


if __name__ == "__main__":
    root = tk.Tk()
    CalibrationGUI(root)
    root.mainloop()
