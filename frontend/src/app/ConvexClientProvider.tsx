"use client";

import { ConvexProvider, ConvexReactClient } from "convex/react";
import { ReactNode } from "react";

export function ConvexClientProvider({ children }: { children: ReactNode }) {
  const deploymentUrl = process.env.NEXT_PUBLIC_CONVEX_URL;

  if (!deploymentUrl) {
    return <>{children}</>;
  }

  const convex = new ConvexReactClient(deploymentUrl);
  return <ConvexProvider client={convex}>{children}</ConvexProvider>;
}
