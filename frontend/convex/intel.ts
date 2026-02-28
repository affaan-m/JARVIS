import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const getByPerson = query({
  args: { personId: v.id("persons") },
  handler: async (ctx, { personId }) => {
    return await ctx.db
      .query("intelFragments")
      .withIndex("by_person", (q) => q.eq("personId", personId))
      .collect();
  },
});

export const create = mutation({
  args: {
    personId: v.id("persons"),
    source: v.string(),
    dataType: v.string(),
    content: v.string(),
    verified: v.optional(v.boolean()),
  },
  handler: async (ctx, { personId, source, dataType, content, verified }) => {
    const now = Date.now();
    const fragmentId = await ctx.db.insert("intelFragments", {
      personId,
      source,
      dataType,
      content,
      verified: verified ?? false,
      timestamp: now,
    });

    // Log activity
    const person = await ctx.db.get(personId);
    await ctx.db.insert("activityLog", {
      type: "research",
      message: `[${source.toUpperCase()}] New ${dataType} intel for ${person?.name ?? "unknown"}`,
      personId,
      agentName: source,
      timestamp: now,
    });

    return fragmentId;
  },
});

export const recentActivity = query({
  handler: async (ctx) => {
    return await ctx.db
      .query("activityLog")
      .order("desc")
      .take(50);
  },
});
