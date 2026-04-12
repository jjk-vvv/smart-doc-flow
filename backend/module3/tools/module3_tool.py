from __future__ import annotations

import argparse
import os
import sys
import threading
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

if __package__ in {None, ""}:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    from backend.module3.core.config import ENV_PATH, read_runtime_settings
    from backend.module3.services.run_service import execute_web_run, run
    from backend.module3.services.storage_service import ensure_storage_dirs
else:
    from ..core.config import ENV_PATH, read_runtime_settings
    from ..services.run_service import execute_web_run, run
    from ..services.storage_service import ensure_storage_dirs


def launch_gui() -> None:
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext
    except Exception as exc:
        raise RuntimeError(f"当前环境无法启动图形界面: {exc}") from exc

    load_dotenv(dotenv_path=ENV_PATH, encoding="utf-8-sig")

    root = tk.Tk()
    root.title("Module3 本地工具")
    root.geometry("980x760")
    root.minsize(900, 680)

    word_var = tk.StringVar()
    template_var = tk.StringVar()
    sheet_var = tk.StringVar()
    header_row_var = tk.StringVar(value="1")
    write_row_var = tk.StringVar(value="2")
    api_mode_var = tk.StringVar(value=os.getenv("OPENAI_API_MODE", "responses").strip().lower() or "responses")
    status_var = tk.StringVar(value="就绪")

    form = tk.Frame(root, padx=14, pady=12)
    form.pack(fill="both", expand=True)
    form.grid_columnconfigure(1, weight=1)

    def add_path_row(
        row: int,
        label_text: str,
        variable: Any,
        filetypes: list[tuple[str, str]],
        save: bool = False,
    ) -> None:
        tk.Label(form, text=label_text).grid(row=row, column=0, sticky="w", pady=6)
        tk.Entry(form, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 8), pady=6)

        def choose_path() -> None:
            initial_dir = str(Path(variable.get()).parent) if variable.get().strip() else os.getcwd()
            if save:
                path = filedialog.asksaveasfilename(
                    title=f"选择{label_text}",
                    initialdir=initial_dir,
                    filetypes=filetypes,
                    defaultextension=filetypes[0][1].replace("*", ""),
                )
            else:
                path = filedialog.askopenfilename(
                    title=f"选择{label_text}",
                    initialdir=initial_dir,
                    filetypes=filetypes,
                )
            if path:
                variable.set(path)

        tk.Button(form, text="浏览", width=9, command=choose_path).grid(row=row, column=2, sticky="e", pady=6)

    add_path_row(0, "Word 数据文件", word_var, [("Word 文件", "*.docx"), ("所有文件", "*.*")], save=False)
    add_path_row(1, "模板文件", template_var, [("模板文件", "*.xlsx *.docx"), ("所有文件", "*.*")], save=False)

    tk.Label(form, text="输出说明").grid(row=2, column=0, sticky="w", pady=6)
    tk.Label(form, text="默认输出为 模板名_filled.*，若重名则自动追加序号").grid(
        row=2,
        column=1,
        columnspan=2,
        sticky="w",
        pady=6,
    )

    tk.Label(form, text="工作表名(可选)").grid(row=3, column=0, sticky="w", pady=6)
    tk.Entry(form, textvariable=sheet_var).grid(row=3, column=1, sticky="ew", padx=(8, 8), pady=6)
    tk.Label(form, text="留空则使用第一个工作表").grid(row=3, column=2, sticky="w", pady=6)

    tk.Label(form, text="表头行号").grid(row=4, column=0, sticky="w", pady=6)
    tk.Entry(form, textvariable=header_row_var).grid(row=4, column=1, sticky="w", padx=(8, 8), pady=6)

    tk.Label(form, text="写入行号").grid(row=5, column=0, sticky="w", pady=6)
    tk.Entry(form, textvariable=write_row_var).grid(row=5, column=1, sticky="w", padx=(8, 8), pady=6)

    tk.Label(form, text="接口模式").grid(row=6, column=0, sticky="w", pady=6)
    tk.OptionMenu(form, api_mode_var, "responses", "chat").grid(row=6, column=1, sticky="w", padx=(8, 8), pady=6)

    tk.Label(form, text="提示词").grid(row=7, column=0, sticky="nw", pady=6)
    prompt_text = tk.Text(form, height=8, wrap="word")
    prompt_text.grid(row=7, column=1, columnspan=2, sticky="nsew", padx=(8, 0), pady=6)
    form.grid_rowconfigure(7, weight=1)

    tk.Label(form, text="模型过程输出").grid(row=8, column=0, sticky="nw", pady=6)
    log_text = scrolledtext.ScrolledText(form, height=10, wrap="word", state="disabled")
    log_text.grid(row=8, column=1, columnspan=2, sticky="nsew", padx=(8, 0), pady=6)
    form.grid_rowconfigure(8, weight=1)

    bottom = tk.Frame(form)
    bottom.grid(row=9, column=0, columnspan=3, sticky="ew", pady=(10, 0))
    bottom.grid_columnconfigure(0, weight=1)

    status_label = tk.Label(bottom, textvariable=status_var, anchor="w")
    status_label.grid(row=0, column=0, sticky="ew")

    def validate_int(text_value: str, field_name: str) -> int:
        try:
            value = int(text_value.strip())
        except ValueError as exc:
            raise ValueError(f"{field_name} 必须是整数") from exc
        if value <= 0:
            raise ValueError(f"{field_name} 必须大于 0")
        return value

    def set_busy(busy: bool) -> None:
        run_button.config(state="disabled" if busy else "normal")
        status_label.config(fg="#0b5394" if busy else "#1f1f1f")

    def append_log(message: str) -> None:
        log_text.config(state="normal")
        log_text.insert("end", message.rstrip() + "\n\n")
        log_text.see("end")
        log_text.config(state="disabled")

    def clear_log() -> None:
        log_text.config(state="normal")
        log_text.delete("1.0", "end")
        log_text.config(state="disabled")

    def on_success(result: dict[str, Any]) -> None:
        set_busy(False)
        status_var.set(f"完成: {result['output_path']}")
        messagebox.showinfo(
            "执行成功",
            "\n".join(
                [
                    "处理完成",
                    f"模板工作表: {result['sheet_name']}",
                    f"表头数量: {result['header_count']}",
                    f"填充行数: {result['row_count']}",
                    f"输出文件: {result['output_path']}",
                ]
            ),
        )

    def on_error(message: str) -> None:
        set_busy(False)
        status_var.set("执行失败")
        messagebox.showerror("执行失败", message)

    def do_run() -> None:
        prompt_value = prompt_text.get("1.0", "end").strip()
        word_value = word_var.get().strip()
        template_value = template_var.get().strip()

        if not word_value:
            messagebox.showwarning("参数不完整", "请先选择 Word 数据文件")
            return
        if not template_value:
            messagebox.showwarning("参数不完整", "请先选择模板文件")
            return
        if not prompt_value:
            messagebox.showwarning("参数不完整", "请填写提示词")
            return

        try:
            header_row = validate_int(header_row_var.get(), "表头行号")
            write_row = validate_int(write_row_var.get(), "写入行号")
        except ValueError as exc:
            messagebox.showwarning("参数错误", str(exc))
            return

        args = argparse.Namespace(
            word=word_value,
            template=template_value,
            prompt=prompt_value,
            output=None,
            json_output=None,
            sheet=sheet_var.get().strip() or None,
            header_row=header_row,
            write_row=write_row,
            api_mode=api_mode_var.get().strip().lower() or None,
            gui=False,
            serve=False,
            host="127.0.0.1",
            port=8123,
        )

        clear_log()
        set_busy(True)
        status_var.set("处理中，请稍候...")
        append_log("[启动] 已提交任务，等待模型返回。")

        def worker() -> None:
            def gui_logger(message: str) -> None:
                root.after(0, lambda msg=message: append_log(msg))

            try:
                result = run(args, logger=gui_logger)
            except Exception as exc:
                err_msg = str(exc)
                root.after(0, lambda msg=err_msg: on_error(msg))
                return
            root.after(0, lambda: on_success(result))

        threading.Thread(target=worker, daemon=True).start()

    run_button = tk.Button(bottom, text="开始处理", width=12, command=do_run)
    run_button.grid(row=0, column=1, sticky="e")

    root.mainloop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Module3 本地工具")
    parser.add_argument("--word", help="Word 数据源路径（.docx）")
    parser.add_argument("--template", help="模板路径（.xlsx / .docx）")
    parser.add_argument("--prompt", help="自定义抽取提示词")
    parser.add_argument("--output", help="输出模板路径，不填则自动生成 模板名_filled.*")
    parser.add_argument("--json-output", help="可选：额外输出 JSON 文件")
    parser.add_argument("--sheet", help="可选：指定工作表名，不填则取第一个")
    parser.add_argument("--header-row", type=int, default=1, help="表头行号，默认 1")
    parser.add_argument("--write-row", type=int, default=2, help="写入行号，默认 2")
    parser.add_argument("--api-mode", choices=["responses", "chat"], help="接口模式：responses 或 chat")
    parser.add_argument("--gui", action="store_true", help="启动图形界面")
    parser.add_argument("--serve", action="store_true", help="启动 FastAPI 服务")
    parser.add_argument("--host", default="127.0.0.1", help="服务监听地址，默认 127.0.0.1")
    parser.add_argument("--port", type=int, default=8123, help="服务端口，默认 8123")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.serve:
        import uvicorn

        ensure_storage_dirs()
        if __package__:
            from ..main import app as module_app
        else:
            from backend.module3.main import app as module_app
        uvicorn.run(module_app, host=args.host, port=args.port)
        return

    if args.gui or len(sys.argv) == 1:
        try:
            launch_gui()
        except Exception as exc:
            print(f"启动图形界面失败: {exc}", file=sys.stderr)
            sys.exit(1)
        return

    missing = [flag for flag in ("word", "template", "prompt") if not getattr(args, flag)]
    if missing:
        parser.error("命令行模式需要 --word --template --prompt，或使用 --gui 启动图形界面")

    try:
        run(args, logger=print)
    except Exception as exc:
        print(f"执行失败: {exc}", file=sys.stderr)
        sys.exit(1)


__all__ = [
    "build_parser",
    "ensure_storage_dirs",
    "execute_web_run",
    "launch_gui",
    "main",
    "read_runtime_settings",
    "run",
]


if __name__ == "__main__":
    main()
