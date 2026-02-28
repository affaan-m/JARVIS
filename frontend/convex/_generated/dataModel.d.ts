/* eslint-disable */
/**
 * Generated data model types — stub for local development.
 * Run `npx convex dev` to replace with real generated types.
 */
import type { GenericDataModel, GenericDocument, GenericId } from "convex/server";

export type Id<TableName extends string> = GenericId<TableName>;

type PersonDossier = {
  summary: string;
  title?: string;
  company?: string;
  workHistory: { role: string; company: string; period?: string }[];
  education: { school: string; degree?: string }[];
  socialProfiles: {
    linkedin?: string;
    twitter?: string;
    instagram?: string;
    github?: string;
    website?: string;
  };
  notableActivity: string[];
  conversationHooks: string[];
  riskFlags: string[];
};

export type DataModel = {
  captures: {
    document: {
      _id: Id<"captures">;
      _creationTime: number;
      imageUrl: string;
      timestamp: number;
      source: string;
      status: "pending" | "identifying" | "identified" | "failed";
      personId?: Id<"persons">;
    };
    fieldPaths:
      | "_id"
      | "_creationTime"
      | "imageUrl"
      | "timestamp"
      | "source"
      | "status"
      | "personId";
    indexes: {};
    searchIndexes: {};
    vectorIndexes: {};
  };
  persons: {
    document: {
      _id: Id<"persons">;
      _creationTime: number;
      name: string;
      photoUrl: string;
      confidence: number;
      status: "identified" | "researching" | "synthesizing" | "complete";
      boardPosition: { x: number; y: number };
      dossier?: PersonDossier;
      createdAt: number;
      updatedAt: number;
    };
    fieldPaths:
      | "_id"
      | "_creationTime"
      | "name"
      | "photoUrl"
      | "confidence"
      | "status"
      | "boardPosition"
      | "dossier"
      | "createdAt"
      | "updatedAt";
    indexes: {};
    searchIndexes: {};
    vectorIndexes: {};
  };
  intelFragments: {
    document: {
      _id: Id<"intelFragments">;
      _creationTime: number;
      personId: Id<"persons">;
      source: string;
      dataType: string;
      content: string;
      verified: boolean;
      timestamp: number;
    };
    fieldPaths:
      | "_id"
      | "_creationTime"
      | "personId"
      | "source"
      | "dataType"
      | "content"
      | "verified"
      | "timestamp";
    indexes: { by_person: ["personId"] };
    searchIndexes: {};
    vectorIndexes: {};
  };
  connections: {
    document: {
      _id: Id<"connections">;
      _creationTime: number;
      personAId: Id<"persons">;
      personBId: Id<"persons">;
      relationshipType: string;
      description: string;
    };
    fieldPaths:
      | "_id"
      | "_creationTime"
      | "personAId"
      | "personBId"
      | "relationshipType"
      | "description";
    indexes: { by_person_a: ["personAId"]; by_person_b: ["personBId"] };
    searchIndexes: {};
    vectorIndexes: {};
  };
  activityLog: {
    document: {
      _id: Id<"activityLog">;
      _creationTime: number;
      type: string;
      message: string;
      personId?: Id<"persons">;
      agentName?: string;
      timestamp: number;
    };
    fieldPaths:
      | "_id"
      | "_creationTime"
      | "type"
      | "message"
      | "personId"
      | "agentName"
      | "timestamp";
    indexes: {};
    searchIndexes: {};
    vectorIndexes: {};
  };
};

export type Doc<TableName extends keyof DataModel> =
  DataModel[TableName]["document"];
