"use client";

/**
 * Modal dialog and side drawer on the native <dialog> element: showModal() gives
 * focus containment, Escape to close, inert background and a backdrop for free, so
 * there is no focus trap code to get wrong.
 */

import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface BaseProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
}

export function useModal(open: boolean) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return ref;
}

function Shell({
  variant,
  open,
  onClose,
  title,
  description,
  children,
  footer,
  className,
}: BaseProps & { variant: "dialog" | "drawer" }) {
  const ref = useModal(open);
  const titleId = useId();
  const descriptionId = useId();

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onClose={onClose}
      // A click whose target is the dialog itself landed on the backdrop: the
      // content wrapper below covers the whole box. Escape is handled natively.
      onClick={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      className={cn(
        "bg-surface p-0 text-foreground shadow-popover backdrop:bg-black/45 open:flex",
        variant === "dialog"
          ? "hl-pop m-auto max-h-[calc(100dvh-2rem)] w-[calc(100%-2rem)] max-w-lg rounded-xl border border-border"
          : "hl-slide ml-auto mr-0 h-dvh max-h-dvh w-full max-w-2xl border-l border-border",
        className,
      )}
    >
      {open && (
        <div className="flex max-h-full w-full flex-col">
          <header className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
            <div className="min-w-0 space-y-1">
              <h2 id={titleId} className="text-base font-semibold">
                {title}
              </h2>
              {description && (
                <div id={descriptionId} className="text-sm text-muted-foreground">
                  {description}
                </div>
              )}
            </div>
            <Button variant="ghost" size="icon-sm" aria-label="Close" onClick={onClose} className="-mr-2 -mt-1">
              <X className="size-4" aria-hidden />
            </Button>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">{children}</div>
          {footer && (
            <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-border px-5 py-3">
              {footer}
            </footer>
          )}
        </div>
      )}
    </dialog>
  );
}

export function Dialog(props: BaseProps) {
  return <Shell variant="dialog" {...props} />;
}

export function Drawer(props: BaseProps) {
  return <Shell variant="drawer" {...props} />;
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  description,
  confirmLabel = "Confirm",
  tone = "danger",
  pending = false,
  children,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  description?: ReactNode;
  confirmLabel?: string;
  tone?: "danger" | "primary";
  pending?: boolean;
  children?: ReactNode;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      description={description}
      footer={
        <>
          <Button variant="outline" onClick={onClose} disabled={pending}>
            Cancel
          </Button>
          <Button variant={tone === "danger" ? "danger" : "primary"} onClick={onConfirm} loading={pending}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  );
}
