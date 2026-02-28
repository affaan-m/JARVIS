/* eslint-disable */
/**
 * Generated API types — stub for local development.
 * Run `npx convex dev` to replace with real generated types.
 */

import type { ApiFromModules } from "convex/server";

// We declare the shape that matches our module exports
declare const api: {
  persons: {
    listAll: any;
    getById: any;
    getByStatus: any;
    create: any;
    updateStatus: any;
    updateDossier: any;
    updatePosition: any;
  };
  intel: {
    getByPerson: any;
    create: any;
    recentActivity: any;
  };
  connections: {
    listAll: any;
    getForPerson: any;
    create: any;
  };
  captures: {
    create: any;
    updateStatus: any;
    listRecent: any;
  };
};

export { api };
