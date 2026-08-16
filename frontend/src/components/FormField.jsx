import React from 'react'
import { classNames } from '../utils/validators'

export default function FormField({
  label,
  required,
  error,
  icon,
  type = 'text',
  value,
  onChange,
  onBlur,
  placeholder,
  maxLength,
  suffix,        // 可选，后缀按钮内容
  suffixDisabled,
  onSuffixClick,
  inputClassName = '',
  autoComplete = 'on'
}) {
  return (
    <div className="form-group">
      {label && (
        <label className="form-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}
      <div className="form-input-wrap">
        <input
          type={type}
          className={classNames(
            'form-input',
            suffix && 'has-suffix',
            error && 'form-input-error',
            inputClassName
          )}
          value={value}
          onChange={(e) => onChange && onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder}
          maxLength={maxLength}
          autoComplete={autoComplete}
        />
        {icon && <span className="form-input-icon">{icon}</span>}
        {suffix && (
          <button
            type="button"
            className="form-suffix-btn"
            disabled={suffixDisabled}
            onClick={onSuffixClick}
          >
            {suffix}
          </button>
        )}
      </div>
      {error && <div className="form-error">{error}</div>}
    </div>
  )
}
