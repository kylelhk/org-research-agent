"""The small window that asks which suburbs a run should research."""

from __future__ import annotations

from collections.abc import Sequence

TITLE = "Research agent"
HINT = "To add more than one suburb, separate them with commas,\nfor example: Bentley,St James"


class WindowUnavailableError(Exception):
    """Raised when this Python can't show windows (no tkinter)."""


class SuburbWindow:
    """Tickboxes for the usual suburbs, an Others box, and Cancel and OK buttons."""

    def __init__(self, usual: Sequence[str]) -> None:
        try:
            import tkinter as tk
            from tkinter import messagebox, ttk
        except ImportError as error:
            raise WindowUnavailableError(str(error)) from error
        self._tk, self._messagebox = tk, messagebox

        root = tk.Tk()
        root.title(TITLE)
        root.resizable(False, False)
        self.root = root
        self._choice = tk.StringVar(master=root)
        root.protocol("WM_DELETE_WINDOW", lambda: self._choice.set("cancel"))

        frame = ttk.Frame(root, padding=(20, 16, 20, 14))
        frame.grid()
        ttk.Label(
            frame, text="Which suburbs should this run research?", font=("", 13, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        self._ticks: list[tuple[str, object]] = []
        for row, name in enumerate(usual, start=1):
            ticked = tk.BooleanVar(master=root, value=True)
            ttk.Checkbutton(frame, text=name, variable=ticked).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2
            )
            self._ticks.append((name, ticked))

        row = len(usual) + 1
        ttk.Label(frame, text="Others:").grid(row=row, column=0, sticky="w", pady=(8, 2))
        self._others = ttk.Entry(frame, width=34)
        self._others.grid(row=row, column=1, sticky="we", padx=(8, 0), pady=(8, 2))
        ttk.Label(frame, text=HINT, foreground="gray").grid(
            row=row + 1, column=0, columnspan=2, sticky="w", pady=(4, 0)
        )
        self._status = ttk.Label(frame, text="", foreground="gray")
        self._status.grid(row=row + 2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(frame)
        buttons.grid(row=row + 3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="Cancel", command=lambda: self._choice.set("cancel")).grid(
            row=0, column=0, padx=(0, 8)
        )
        # OK is the blue default button. Beside it, a Mac draws Cancel plain, as in its
        # own dialogs; Cancel still works. Return means OK, and Escape means Cancel.
        self._ok = ttk.Button(
            buttons, text="OK", default="active", command=lambda: self._choice.set("ok")
        )
        self._ok.grid(row=0, column=1)
        root.bind("<Return>", lambda _event: self._choice.set("ok"))
        root.bind("<Escape>", lambda _event: self._choice.set("cancel"))

    def _bring_to_front(self) -> None:
        root = self.root
        root.update_idletasks()
        x = (root.winfo_screenwidth() - root.winfo_reqwidth()) // 2
        y = (root.winfo_screenheight() - root.winfo_reqheight()) // 3
        root.geometry(f"+{x}+{y}")
        root.deiconify()
        root.lift()
        # Opened from Terminal, the window can start behind it; float it up once.
        root.attributes("-topmost", True)
        root.after(500, lambda: root.attributes("-topmost", False))
        root.focus_force()
        self._others.focus_set()

    def ask(self) -> tuple[list[str], str] | None:
        self._choice.set("")
        self._bring_to_front()
        self.root.wait_variable(self._choice)
        if self._choice.get() != "ok":
            return None
        ticked = [name for name, variable in self._ticks if variable.get()]
        return ticked, self._others.get()

    def warn(self, message: str) -> None:
        self._messagebox.showwarning(TITLE, message, parent=self.root)

    def confirm(self, message: str) -> bool:
        return self._messagebox.askyesno(TITLE, message, icon="warning", parent=self.root)

    def busy(self, busy: bool) -> None:
        self._status.configure(text="Checking the suburbs…" if busy else "")
        self._ok.state(["disabled"] if busy else ["!disabled"])
        self.root.configure(cursor="watch" if busy else "")
        self.root.update()

    def close(self) -> None:
        # Hide it and let the Mac redraw before destroying it. Otherwise the window stays
        # on screen, frozen, while the run carries on without the window's event loop.
        self.root.withdraw()
        self.root.update()
        self.root.destroy()
