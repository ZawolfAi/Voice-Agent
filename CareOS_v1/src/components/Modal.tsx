import { useEffect, useRef, type ReactNode } from "react";

export function Modal({ children, close, label }: { children: ReactNode; close: () => void; label?: string }) {
  const modalRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    modalRef.current?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
      if (event.key !== "Tab" || !modalRef.current) return;
      const focusable = modalRef.current.querySelectorAll<HTMLElement>("button, input, textarea, select, a[href]");
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => { document.removeEventListener("keydown", onKeyDown); previous?.focus(); };
  }, [close]);
  return <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={label} onClick={close}><div ref={modalRef} className="modal" tabIndex={-1} onClick={(event) => event.stopPropagation()}>{children}</div></div>;
}