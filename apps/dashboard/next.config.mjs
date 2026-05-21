import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(dirname(dirname(fileURLToPath(import.meta.url))));

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ["@pentecostal-live/types"],
  turbopack: {
    root: join(root)
  }
};

export default nextConfig;
