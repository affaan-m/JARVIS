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

// Backend-compatible generic store (upsert by capture_id field in data)
export const store = mutation({
  args: { data: v.any() },
  handler: async (ctx, { data }) => {
    const captureId = data.capture_id ?? `cap_${Date.now()}`;
    const source = data.source ?? "manual_upload";
    const status = data.status ?? "pending";

    // Map to schema-compatible status
    const validStatus = ["pending", "identifying", "identified", "failed"].includes(status)
      ? status as "pending" | "identifying" | "identified" | "failed"
      : "pending";

    // Check if capture already exists by scanning recent captures
    const existing = await ctx.db
      .query("captures")
      .order("desc")
      .take(100);
    const match = existing.find(
      (c: Record<string, unknown>) => c.imageUrl === captureId
    );

    if (match) {
      await ctx.db.patch(match._id, { status: validStatus });
      return match._id;
    }

    const id = await ctx.db.insert("captures", {
      imageUrl: captureId,
      timestamp: Date.now(),
      source,
      status: validStatus,
    });

    await ctx.db.insert("activityLog", {
      type: "capture",
      message: `New capture via ${source}`,
      timestamp: Date.now(),
    });

    return id;
  },
});
