import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

// === QUERIES ===

export const listAll = query({
  handler: async (ctx) => {
    return await ctx.db.query("persons").collect();
  },
});

export const getById = query({
  args: { id: v.id("persons") },
  handler: async (ctx, { id }) => {
    return await ctx.db.get(id);
  },
});

export const getByStatus = query({
  args: {
    status: v.union(
      v.literal("identified"),
      v.literal("researching"),
      v.literal("synthesizing"),
      v.literal("complete")
    ),
  },
  handler: async (ctx, { status }) => {
    return await ctx.db
      .query("persons")
      .filter((q) => q.eq(q.field("status"), status))
      .collect();
  },
});

// === MUTATIONS ===

export const create = mutation({
  args: {
    name: v.string(),
    photoUrl: v.string(),
    confidence: v.number(),
    boardPosition: v.optional(v.object({ x: v.number(), y: v.number() })),
  },
  handler: async (ctx, { name, photoUrl, confidence, boardPosition }) => {
    const now = Date.now();
    // Auto-position: random spot on the board if not provided
    const pos = boardPosition ?? {
      x: 100 + Math.random() * 800,
      y: 100 + Math.random() * 500,
    };

    const personId = await ctx.db.insert("persons", {
      name,
      photoUrl,
      confidence,
      status: "identified",
      boardPosition: pos,
      createdAt: now,
      updatedAt: now,
    });

    // Log the activity
    await ctx.db.insert("activityLog", {
      type: "identify",
      message: `Identified: ${name} (${Math.round(confidence * 100)}% confidence)`,
      personId,
      timestamp: now,
    });

    return personId;
  },
});

export const updateStatus = mutation({
  args: {
    id: v.id("persons"),
    status: v.union(
      v.literal("identified"),
      v.literal("researching"),
      v.literal("synthesizing"),
      v.literal("complete")
    ),
  },
  handler: async (ctx, { id, status }) => {
    await ctx.db.patch(id, { status, updatedAt: Date.now() });

    const person = await ctx.db.get(id);
    if (person) {
      await ctx.db.insert("activityLog", {
        type: status === "complete" ? "complete" : "research",
        message: `${person.name}: status → ${status.toUpperCase()}`,
        personId: id,
        timestamp: Date.now(),
      });
    }
  },
});

export const updateDossier = mutation({
  args: {
    id: v.id("persons"),
    dossier: v.object({
      summary: v.string(),
      title: v.optional(v.string()),
      company: v.optional(v.string()),
      workHistory: v.array(
        v.object({
          role: v.string(),
          company: v.string(),
          period: v.optional(v.string()),
        })
      ),
      education: v.array(
        v.object({
          school: v.string(),
          degree: v.optional(v.string()),
        })
      ),
      socialProfiles: v.object({
        linkedin: v.optional(v.string()),
        twitter: v.optional(v.string()),
        instagram: v.optional(v.string()),
        github: v.optional(v.string()),
        website: v.optional(v.string()),
      }),
      notableActivity: v.array(v.string()),
      conversationHooks: v.array(v.string()),
      riskFlags: v.array(v.string()),
    }),
  },
  handler: async (ctx, { id, dossier }) => {
    await ctx.db.patch(id, {
      dossier,
      status: "complete",
      updatedAt: Date.now(),
    });
  },
});

export const updatePosition = mutation({
  args: {
    id: v.id("persons"),
    boardPosition: v.object({ x: v.number(), y: v.number() }),
  },
  handler: async (ctx, { id, boardPosition }) => {
    await ctx.db.patch(id, { boardPosition });
  },
});

// Backend-compatible generic store (creates person from pipeline data)
export const store = mutation({
  args: { data: v.any() },
  handler: async (ctx, { data }) => {
    const now = Date.now();
    const name = data.name ?? "Unknown";
    const confidence = typeof data.confidence === "number" ? data.confidence : 0.5;

    const personId = await ctx.db.insert("persons", {
      name,
      photoUrl: data.photoUrl ?? "",
      confidence,
      status: "identified",
      boardPosition: {
        x: 100 + Math.random() * 800,
        y: 100 + Math.random() * 500,
      },
      createdAt: now,
      updatedAt: now,
    });

    await ctx.db.insert("activityLog", {
      type: "identify",
      message: `Identified: ${name} (${Math.round(confidence * 100)}% confidence)`,
      personId,
      timestamp: now,
    });

    return personId;
  },
});

// Backend-compatible generic update (patches person by person_id lookup)
export const update = mutation({
  args: {
    person_id: v.string(),
    data: v.any(),
  },
  handler: async (ctx, { person_id, data }) => {
    // Find person by scanning (person_id is a pipeline-side ID, not Convex _id)
    const all = await ctx.db.query("persons").collect();
    // Try matching by _id first, then by name or other field
    const match = all.find(
      (p) => p._id === person_id || (p as Record<string, unknown>)["person_id"] === person_id
    );

    if (!match) {
      // Silently skip — person may have been created with InMemory gateway
      return;
    }

    const patch: Record<string, unknown> = { updatedAt: Date.now() };

    // Map pipeline status to Convex schema status
    if (data.status) {
      const statusMap: Record<string, string> = {
        detected: "identified",
        identified: "identified",
        enriching: "researching",
        enriched: "complete",
        enriched_no_synthesis: "synthesizing",
        synthesis_failed: "identified",
      };
      const mappedStatus = statusMap[data.status] ?? "identified";
      patch.status = mappedStatus;
    }

    if (data.summary) patch.dossier = {
      summary: data.summary,
      title: data.occupation ?? undefined,
      company: data.organization ?? undefined,
      workHistory: data.dossier?.work_history ?? [],
      education: data.dossier?.education ?? [],
      socialProfiles: data.dossier?.social_profiles ?? {
        linkedin: undefined,
        twitter: undefined,
        instagram: undefined,
        github: undefined,
        website: undefined,
      },
      notableActivity: data.dossier?.notable_activity ?? [],
      conversationHooks: data.dossier?.conversation_hooks ?? [],
      riskFlags: data.dossier?.risk_flags ?? [],
    };

    await ctx.db.patch(match._id, patch);
  },
});

// Backend-compatible get by person_id
export const get = query({
  args: { person_id: v.string() },
  handler: async (ctx, { person_id }) => {
    const all = await ctx.db.query("persons").collect();
    return all.find(
      (p) => p._id === person_id || (p as Record<string, unknown>)["person_id"] === person_id
    ) ?? null;
  },
});
