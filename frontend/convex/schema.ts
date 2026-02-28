// SPECTER — Convex Schema
// Real-time person intelligence database
import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  captures: defineTable({
    imageUrl: v.string(),
    timestamp: v.number(),
    source: v.string(), // "glasses" | "telegram" | "upload"
    status: v.union(
      v.literal("pending"),
      v.literal("identifying"),
      v.literal("identified"),
      v.literal("failed")
    ),
    personId: v.optional(v.id("persons")),
  }),

  persons: defineTable({
    name: v.string(),
    photoUrl: v.string(),
    confidence: v.number(), // 0-1 identification confidence
    status: v.union(
      v.literal("identified"),
      v.literal("researching"),
      v.literal("synthesizing"),
      v.literal("complete")
    ),
    boardPosition: v.object({ x: v.number(), y: v.number() }),
    dossier: v.optional(
      v.object({
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
      })
    ),
    createdAt: v.number(),
    updatedAt: v.number(),
  }),

  intelFragments: defineTable({
    personId: v.id("persons"),
    source: v.string(), // "exa" | "linkedin" | "twitter" | "google" | "pimeyes"
    dataType: v.string(), // "profile" | "post" | "article" | "connection"
    content: v.string(), // JSON string of extracted data
    verified: v.boolean(),
    timestamp: v.number(),
  }).index("by_person", ["personId"]),

  connections: defineTable({
    personAId: v.id("persons"),
    personBId: v.id("persons"),
    relationshipType: v.string(), // "colleague" | "classmate" | "mutual_follow"
    description: v.string(),
  })
    .index("by_person_a", ["personAId"])
    .index("by_person_b", ["personBId"]),

  // Live activity feed for the sidebar
  activityLog: defineTable({
    type: v.string(), // "capture" | "identify" | "research" | "complete"
    message: v.string(),
    personId: v.optional(v.id("persons")),
    agentName: v.optional(v.string()),
    timestamp: v.number(),
  }),
});
