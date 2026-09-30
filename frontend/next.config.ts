import path from "node:path";

import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    // Without this, Turbopack walks up and picks the repository root (which has
    // no package.json) as its root, and then cannot resolve tailwindcss from
    // frontend/node_modules. Pin the root to this directory.
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
