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
