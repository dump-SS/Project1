import { useState } from 'react'

/**
 * 可复用的学习功能区组件：中英文标签 → 文本框 →（可选）校验警告。
 * 「进入」键为页面统一按钮，见 App.jsx。
 *
 * @param {string}   cnLabel     中文功能名，如「学习时间设置」
 * @param {string}   enLabel     英文功能名，如「Study Time Setting」
 * @param {string}   placeholder 文本框占位提示
 * @param {Function} [validate]  可选校验函数：传入时开启输入校验，返回 false 则在下方显示红色警告
 */
export default function StudyEditor({ cnLabel, enLabel, placeholder, validate }) {
  const [value, setValue] = useState('')
  const invalid = validate ? !validate(value) : false

  const handleChange = (event) => {
    setValue(event.target.value)
  }

  return (
    <section className="study-editor">
      <label className="editor-label">
        {cnLabel}
        <span className="en">{enLabel}</span>
      </label>

      <div className="editor-field">
        <input
          className="editor-input"
          type="text"
          value={value}
          placeholder={placeholder}
          onChange={handleChange}
        />
        <span className="editor-suffix" aria-hidden="true">
          e<sup>x</sup>
        </span>
      </div>

      {invalid && <p className="editor-warning">无效输入 Invalid input</p>}
    </section>
  )
}