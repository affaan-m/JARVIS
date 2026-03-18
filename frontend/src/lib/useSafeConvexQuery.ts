"use client";

import { useConvexAvailable } from "@/app/ConvexClientProvider";
import { useQuery } from "convex/react";
import { api } from "../../convex/_generated/api";

/**
 * Safely query Convex persons — returns undefined when Convex isn't configured
 * instead of throwing "Could not find Convex client".
 */
export function useSafeConvexPersons() {
  const available = useConvexAvailable();
  // Hooks must be called unconditionally, but useQuery will throw without a provider.
  // Since ConvexClientProvider only wraps children in ConvexProvider when configured,
  // we must not call useQuery when Convex is unavailable.
  // Workaround: this hook is only safe to call when available=true.
  // When available=false, we skip entirely.
  if (!available) return undefined;
  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useQuery(api.persons.listAll);
}
