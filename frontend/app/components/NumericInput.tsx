"use client";

import type { FocusEvent, InputHTMLAttributes } from "react";
import { clearZeroOnFocusValue } from "../lib/numeric-input.mjs";

interface NumericInputProps
  extends Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> {
  value: string;
  onValueChange: (value: string) => void;
}

export function NumericInput({ value, onValueChange, onFocus, ...props }: NumericInputProps) {
  const handleFocus = (event: FocusEvent<HTMLInputElement>) => {
    const editableValue = clearZeroOnFocusValue(value);
    if (editableValue !== value) onValueChange(editableValue);
    onFocus?.(event);
  };

  return (
    <input
      {...props}
      type="number"
      value={value}
      onChange={(event) => onValueChange(event.target.value)}
      onFocus={handleFocus}
    />
  );
}
