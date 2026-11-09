import type { NextConfig } from 'next'

const apiBase = process.env.API_PROXY_TARGET || process.env.NEXT_PUBLIC_API_BASE_URL || ''

const nextConfig: NextConfig = {
  async rewrites() {
    if (!apiBase) return []
    const target = apiBase.replace(/\/$/, '')
    return [
      {
        source: '/v1/:path*',
        destination: `${target}/v1/:path*`,
      },
    ]
  },
}

export default nextConfig
