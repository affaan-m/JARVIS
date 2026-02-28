/* eslint-disable */
/**
 * Generated server types — stub for local development.
 * Run `npx convex dev` to replace with real generated types.
 */
import type { DataModel } from "./dataModel";
import {
  QueryBuilder,
  MutationBuilder,
  ActionBuilder,
} from "convex/server";

export declare const query: QueryBuilder<DataModel, "public">;
export declare const mutation: MutationBuilder<DataModel, "public">;
export declare const action: ActionBuilder<DataModel, "public">;
export declare const internalQuery: QueryBuilder<DataModel, "internal">;
export declare const internalMutation: MutationBuilder<DataModel, "internal">;
export declare const internalAction: ActionBuilder<DataModel, "internal">;
