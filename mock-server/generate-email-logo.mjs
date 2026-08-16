// 一次性脚本：把品牌图标读取并 base64 编码，写入 email-logo.b64.js
// 邮件模板通过 import 引入此 data URI，渲染时直接嵌入 HTML，避免外部请求
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 邮件右下角用方形 icon 更合适（占位小、品牌一致）
const SRC = path.join(__dirname, '..', 'frontend', 'public', 'brand', 'favicon.png')
const OUT_JS = path.join(__dirname, 'email-logo.b64.js')

const buf = fs.readFileSync(SRC)
const b64 = buf.toString('base64')
const dataUri = `data:image/png;base64,${b64}`

fs.writeFileSync(
  OUT_JS,
  `// 自动生成：EpochX 邮件 logo（base64 内联，避免邮件客户端拦截外链图片）
export const EMAIL_LOGO_DATA_URI = ${JSON.stringify(dataUri)}
`,
  'utf8'
)

console.log(`OK: ${OUT_JS}`)
console.log(`  source: ${SRC} (${buf.length} bytes)`)
console.log(`  base64: ${b64.length} chars`)
