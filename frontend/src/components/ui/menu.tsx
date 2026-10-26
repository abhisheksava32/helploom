"use client";

/**
 * Dropdown menu following the WAI-ARIA menu button pattern: the trigger opens the
 * menu and focuses the first item, arrow keys move, Home and End jump, Escape
 * closes and returns focus, Tab and outside clicks close.
 */

import Link from "next/link";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type ComponentProps,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { cn } from "@/lib/cn";

function menuItems(menu: HTMLElement | null): HTMLElement[] {
  if (!menu) return [];
  return Array.from(menu.querySelectorAll<HTMLElement>('[role="menuitem"]:not([aria-disabled="true"])'));
}

export function Menu({
  label,
  trigger,
  triggerClassName,
  align = "start",
  side = "bottom",
  className,
  children,
}: {
  /** Accessible name of the trigger when its content is not descriptive text. */
  label?: string;
  trigger: ReactNode;
  triggerClassName?: string;
  align?: "start" | "end";
  side?: "bottom" | "top";
  className?: string;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    if (!open) return;
    menuItems(menuRef.current)[0]?.focus();
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) triggerRef.current?.focus();
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = menuItems(menuRef.current);
    const index = items.indexOf(document.activeElement as HTMLElement);
    const focus = (next: number) => items[(next + items.length) % items.length]?.focus();
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        focus(index + 1);
        break;
      case "ArrowUp":
        event.preventDefault();
        focus(index - 1);
        break;
      case "Home":
        event.preventDefault();
        focus(0);
        break;
      case "End":
        event.preventDefault();
        focus(items.length - 1);
        break;
      case "Escape":
        event.preventDefault();
        close(true);
        break;
      case "Tab":
        setOpen(false);
        break;
    }
  };

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            setOpen(true);
          }
        }}
        className={triggerClassName}
      >
        {trigger}
      </button>
      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          tabIndex={-1}
          onKeyDown={onMenuKeyDown}
          // Selecting an item closes the menu; items stop propagation to stay open.
          onClick={() => close(false)}
          className={cn(
            "hl-pop absolute z-50 min-w-56 rounded-lg border border-border bg-surface p-1 shadow-popover",
            align === "end" ? "right-0" : "left-0",
            side === "top" ? "bottom-full mb-2" : "top-full mt-2",
          )}
        >
          {children}
        </div>
      )}
    </div>
  );
}

const itemClasses =
  "flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-sm text-foreground outline-none " +
  "hover:bg-surface-muted focus-visible:bg-surface-muted focus-visible:outline-none";

export function MenuItem({ className, ...props }: ComponentProps<"button">) {
  return <button type="button" role="menuitem" tabIndex={-1} className={cn(itemClasses, className)} {...props} />;
}

export function MenuLink({ className, ...props }: ComponentProps<typeof Link>) {
  return <Link role="menuitem" tabIndex={-1} className={cn(itemClasses, className)} {...props} />;
}

export function MenuLabel({ children }: { children: ReactNode }) {
  return (
    <div role="presentation" className="px-2.5 pb-1 pt-2 text-xs font-medium text-muted-foreground">
      {children}
    </div>
  );
}

export function MenuSeparator() {
  return <div role="separator" className="my-1 h-px bg-border" />;
}
