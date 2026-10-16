import type { ButtonHTMLAttributes, ReactNode } from "react";

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "soft" | "ghost";
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`button button--${variant} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
export function IconButton({
  label,
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      className={`icon-button ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
