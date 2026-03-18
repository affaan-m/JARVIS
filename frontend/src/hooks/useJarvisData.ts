"use client";

import { useQuery } from "convex/react";
import { api } from "../../convex/_generated/api";
import { useConvexAvailable } from "@/app/ConvexClientProvider";
import { demoActivity, demoConnections, demoPersons } from "@/lib/demo-data";
import type { ActivityRecord, ConnectionRecord, PersonRecord } from "@/lib/types";

/**
 * Reads persons from Convex when available, falls back to demo data.
 * The hook can only call useQuery inside a ConvexProvider, so we split
 * into two components: one that queries and one that returns demo data.
 */
function useConvexPersons(): PersonRecord[] | undefined {
  const raw = useQuery(api.persons.listAll);
  if (raw === undefined) return undefined;
  return raw.map((p: Record<string, unknown>): PersonRecord => ({
    _id: String(p._id),
    name: String(p.name),
    photoUrl: String(p.photoUrl),
    confidence: Number(p.confidence),
    status: p.status as PersonRecord["status"],
    boardPosition: p.boardPosition as PersonRecord["boardPosition"],
    dossier: p.dossier as PersonRecord["dossier"],
  }));
}

function useConvexConnections(): ConnectionRecord[] | undefined {
  const raw = useQuery(api.connections.listAll);
  if (raw === undefined) return undefined;
  return raw.map((c: Record<string, unknown>): ConnectionRecord => ({
    _id: String(c._id),
    personAId: String(c.personAId),
    personBId: String(c.personBId),
    relationshipType: String(c.relationshipType),
    description: String(c.description),
  }));
}

function useConvexActivity(): ActivityRecord[] | undefined {
  const raw = useQuery(api.intel.recentActivity);
  if (raw === undefined) return undefined;
  return raw.map((a: Record<string, unknown>): ActivityRecord => ({
    _id: String(a._id),
    type: String(a.type),
    message: String(a.message),
    personId: a.personId ? String(a.personId) : undefined,
    agentName: a.agentName ? String(a.agentName) : undefined,
    timestamp: Number(a.timestamp),
  }));
}

export interface JarvisData {
  persons: PersonRecord[];
  connections: ConnectionRecord[];
  activity: ActivityRecord[];
  isLive: boolean;
  isLoading: boolean;
}

/**
 * Top-level hook: call inside a component that is a descendant of ConvexClientProvider.
 * When NEXT_PUBLIC_CONVEX_URL is set, queries Convex; otherwise returns demo data.
 */
export function useJarvisData(): JarvisData {
  const convexAvailable = useConvexAvailable();

  if (!convexAvailable) {
    return {
      persons: demoPersons,
      connections: demoConnections,
      activity: demoActivity,
      isLive: false,
      isLoading: false,
    };
  }

  // eslint-disable-next-line react-hooks/rules-of-hooks
  return useJarvisDataLive();
}

/** Only called when ConvexProvider is mounted. */
function useJarvisDataLive(): JarvisData {
  const persons = useConvexPersons();
  const connections = useConvexConnections();
  const activity = useConvexActivity();

  const isLoading = persons === undefined || connections === undefined || activity === undefined;

  // While loading from Convex, show demo data so the UI is never blank
  if (isLoading) {
    return {
      persons: persons ?? demoPersons,
      connections: connections ?? demoConnections,
      activity: activity ?? demoActivity,
      isLive: false,
      isLoading: true,
    };
  }

  // If Convex returns empty data, fall back to demo data for the demo
  const hasPersons = persons.length > 0;

  return {
    persons: hasPersons ? persons : demoPersons,
    connections: hasPersons ? connections : demoConnections,
    activity: hasPersons ? activity : demoActivity,
    isLive: hasPersons,
    isLoading: false,
  };
}
