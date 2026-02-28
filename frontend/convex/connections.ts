import { v } from "convex/values";
import { mutation, query } from "./_generated/server";

export const listAll = query({
  handler: async (ctx) => {
    return await ctx.db.query("connections").collect();
  },
});

export const getForPerson = query({
  args: { personId: v.id("persons") },
  handler: async (ctx, { personId }) => {
    const asA = await ctx.db
      .query("connections")
      .withIndex("by_person_a", (q) => q.eq("personAId", personId))
      .collect();
    const asB = await ctx.db
      .query("connections")
      .withIndex("by_person_b", (q) => q.eq("personBId", personId))
      .collect();
    return [...asA, ...asB];
  },
});

export const create = mutation({
  args: {
    personAId: v.id("persons"),
    personBId: v.id("persons"),
    relationshipType: v.string(),
    description: v.string(),
  },
  handler: async (ctx, args) => {
    return await ctx.db.insert("connections", args);
  },
});
