/**
 * TextType —— 源自 React Bits（https://reactbits.dev，MIT + Commons Clause：
 * 产品内可用，禁止打包成组件库转售），-TS-TW 变体源码拷贝进仓库。
 *
 * 本仓库改动（2026-09-25，React 18.3 适配 + 体积优化）：
 * 1. 光标闪烁从 gsap 补间改为 CSS 动画（.lp-caret / lp-caret-blink）——
 *    原版拖 gsap（gzip ~101KB），本组件是全页唯一用到它的地方，删之；
 * 2. 其余逻辑保持原版：无 React 19 专属 API（无 use()/ref-as-prop/Actions），
 *    ref 经 createElement 传给 DOM 元素在 React 18 下合法 → 兼容性 ✓。
 */
import { type ElementType, useEffect, useRef, useState, useMemo } from 'react'

interface TextTypeProps {
  className?: string
  showCursor?: boolean
  cursorCharacter?: string | React.ReactNode
  cursorClassName?: string
  text: string | string[]
  as?: ElementType
  typingSpeed?: number
  initialDelay?: number
  pauseDuration?: number
  loop?: boolean
  textColors?: string[]
  variableSpeed?: { min: number; max: number }
  onSentenceComplete?: (sentence: string, index: number) => void
  startOnVisible?: boolean
  /** 打完最后一句停在原地（不进入删除循环） */
  holdOnComplete?: boolean
}

const TextType = ({
  text,
  as: Component = 'div',
  typingSpeed = 50,
  initialDelay = 0,
  pauseDuration = 2000,
  loop = true,
  className = '',
  showCursor = true,
  cursorCharacter = '|',
  cursorClassName = '',
  textColors = [],
  variableSpeed,
  onSentenceComplete,
  startOnVisible = false,
  holdOnComplete = false,
  ...props
}: TextTypeProps & React.HTMLAttributes<HTMLElement>) => {
  const [displayedText, setDisplayedText] = useState('')
  const [currentCharIndex, setCurrentCharIndex] = useState(0)
  const [currentTextIndex, setCurrentTextIndex] = useState(0)
  const [isVisible, setIsVisible] = useState(!startOnVisible)
  const containerRef = useRef<HTMLElement>(null)

  const textArray = useMemo(() => (Array.isArray(text) ? text : [text]), [text])

  useEffect(() => {
    if (!startOnVisible || !containerRef.current) return
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) setIsVisible(true)
        })
      },
      { threshold: 0.1 },
    )
    observer.observe(containerRef.current)
    return () => observer.disconnect()
  }, [startOnVisible])

  useEffect(() => {
    if (!isVisible) return

    let timeout: ReturnType<typeof setTimeout>
    const currentText = textArray[currentTextIndex]
    const isLast = currentTextIndex === textArray.length - 1

    if (currentCharIndex < currentText.length) {
      const delay = variableSpeed
        ? Math.random() * (variableSpeed.max - variableSpeed.min) + variableSpeed.min
        : typingSpeed
      // 每句第一个字前额外等待 initialDelay
      const entryDelay = currentCharIndex === 0 ? initialDelay : 0
      timeout = setTimeout(() => {
        setDisplayedText((prev) => prev + currentText[currentCharIndex])
        setCurrentCharIndex((prev) => prev + 1)
      }, entryDelay + delay)
    } else if (!(holdOnComplete && isLast)) {
      // 打完当前句：停顿后清屏换下一句（holdOnComplete 时最后一句原地保持）
      timeout = setTimeout(() => {
        if (onSentenceComplete) onSentenceComplete(currentText, currentTextIndex)
        if (isLast && !loop) return
        setCurrentTextIndex((prev) => (prev + 1) % textArray.length)
        setCurrentCharIndex(0)
        setDisplayedText('')
      }, pauseDuration)
    }

    return () => clearTimeout(timeout)
  }, [
    currentCharIndex,
    isVisible,
    typingSpeed,
    pauseDuration,
    textArray,
    currentTextIndex,
    loop,
    initialDelay,
    variableSpeed,
    onSentenceComplete,
    holdOnComplete,
  ])

  const getCurrentTextColor = () =>
    textColors.length === 0 ? 'inherit' : textColors[currentTextIndex % textColors.length]

  return (
    <Component
      ref={containerRef}
      className={`lp-typetype inline-block whitespace-pre-wrap ${className}`}
      {...props}
    >
      <span className="inline" style={{ color: getCurrentTextColor() || 'inherit' }}>
        {displayedText}
      </span>
      {showCursor && (
        <span className={`lp-caret inline-block ${cursorClassName}`}>{cursorCharacter}</span>
      )}
    </Component>
  )
}

export default TextType
