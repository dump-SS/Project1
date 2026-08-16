/**
 * 「进入」键：白色背景，含「进入」与「ENTER」字样，
 * 空链接占位（href="#"），左键可点击。
 */
export default function EnterButton() {
  return (
    <a className="enter-button" href="#" aria-label="进入">
      进入
      <span className="enter-en">ENTER</span>
    </a>
  )
}