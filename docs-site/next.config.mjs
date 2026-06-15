import { createMDX } from 'fumadocs-mdx/next';

/** @type {import('next').NextConfig} */
const config = {
  reactStrictMode: true,
  basePath: '/docs',
  output: 'standalone',
};

const withMDX = createMDX();

export default withMDX(config);
