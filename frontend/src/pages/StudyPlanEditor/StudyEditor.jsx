import { useState } from 'react'

/**
 * 可复用的学习功能区组件：中英文标签 → 文本框 →（可选）校验警告。
 * 「进入」键为页面统一按钮，见 App.jsx。
 *
 * @param {string}   cnLabel     中文功能名，如「学习时间设置」
 * @param {string}   enLabel     英文功能名，如「Study Time Setting」
 * @param {string}   [placeholder]  文本框占位提示
 * @param {Function} [validate]  可选校验函数：传入时开启输入校验，返回 false 则在下方显示红色警告
 * @param {string}   [value]     可选受控值：传入后由外部管理输入框内容（用于程序化填充）
 * @param {Function} [onChange]  受控模式下的变更回调，接收 event
 * @param {string}   [inputType] 输入框类型，'text'（默认）| 'number'（number 时限定 10-600 整数）
 */
export default function StudyEditor({ cnLabel, enLabel, placeholder, validate, value: controlledValue, onChange, inputType = 'text' }) {
  const [internalValue, setInternalValue] = useState('')
  // 受控模式：外部传入 value 时使用外部值，否则退化为内部状态
  const value = controlledValue !== undefined ? controlledValue : internalValue
  const invalid = validate ? !validate(value) : false

  const handleChange = (event) => {
    if (onChange) {
      onChange(event)
    } else {
      setInternalValue(event.target.value)
    }
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
          type={inputType}
          value={value}
          placeholder={placeholder}
          onChange={handleChange}
          {...(inputType === 'number' ? { min: 10, max: 600, step: 1 } : {})}
        />
        <span className="editor-suffix" aria-hidden="true">
          e<sup>x</sup>
        </span>
      </div>

      {invalid && <p className="editor-warning">无效输入 Invalid input</p>}
    </section>
  )
}