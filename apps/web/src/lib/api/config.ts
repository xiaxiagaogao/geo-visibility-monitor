/**
 * 口径与平台配置。**平台清单必须读这里，不许硬编码**（API.md §5）——
 * 接第二个平台时后端改一行，前端零改动。
 */
import type { PlatformsConfig } from '../types'
import { apiFetch } from './client'

export async function fetchPlatforms(): Promise<PlatformsConfig> {
  return apiFetch<PlatformsConfig>('/v1/config/platforms')
}
