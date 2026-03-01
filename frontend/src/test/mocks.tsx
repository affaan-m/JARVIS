import React from "react";
import { vi } from "vitest";

// Mock framer-motion to render plain elements
vi.mock("framer-motion", () => ({
  motion: new Proxy(
    {},
    {
      get: (_target, prop: string) => {
        return React.forwardRef(
          (
            {
              children,
              initial: _initial,
              animate: _animate,
              exit: _exit,
              whileHover: _whileHover,
              transition: _transition,
              ...rest
            }: React.PropsWithChildren<Record<string, unknown>>,
            ref: React.Ref<HTMLElement>
          ) =>
            React.createElement(prop, { ...rest, ref }, children)
        );
      },
    }
  ),
  AnimatePresence: ({ children }: React.PropsWithChildren) => <>{children}</>,
}));

// Mock next/image with a plain img tag
vi.mock("next/image", () => ({
  default: ({
    src,
    alt,
    width,
    height,
    ...rest
  }: {
    src: string;
    alt: string;
    width: number;
    height: number;
    [key: string]: unknown;
  }) => {
    const { unoptimized: _unoptimized, ...imgProps } = rest;
    return <img src={src} alt={alt} width={width} height={height} {...imgProps} />;
  },
}));
