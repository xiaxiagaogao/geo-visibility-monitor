import { BrandsView } from './BrandsView'

/**
 * 品牌列表（A2）。
 *
 * 客户也可达 —— 但 `/v1/brands` 对客户身份**强制**收敛到他的 workspace
 * （`visible_workspace_id`，不是可选参数），所以他看到的就是自己那份。
 */
export default function BrandsPage() {
  return <BrandsView />
}
