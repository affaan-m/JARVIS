import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const create = mutation({
  args: {
    imageUrl: v.string(),
    source: v.string(),
  },
  handler: async (ctx, { imageUrl, source }) => {
    const captureId = await ctx.db.insert("captures", {
      imageUrl,
      timestamp: Date.now(),
      source,
      status: "pending",
    });

    await ctx.db.insert("activityLog", {
      type: "capture",
      message: `New face captured via ${source}`,
      timestamp: Date.now(),
    });

    return captureId;
  },
});

export const updateStatus = mutation({
  args: {
    id: v.id("captures"),
    status: v.union(
      v.literal("pending"),
      v.literal("identifying"),
      v.literal("identified"),
      v.literal("failed")
    ),
    personId: v.optional(v.id("persons")),
  },
  handler: async (ctx, { id, status, personId }) => {
    await ctx.db.patch(id, { status, ...(personId ? { personId } : {}) });
  },
});

export const listRecent = query({
  handler: async (ctx) => {
    return await ctx.db.query("captures").order("desc").take(20);
  },
});
