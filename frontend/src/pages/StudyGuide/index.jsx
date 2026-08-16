import { useState } from 'react'
import StudyEditor from '../StudyPlanEditor/StudyEditor.jsx'
import EnterButton from '../StudyPlanEditor/EnterButton.jsx'
import './index.css'
import './Guide.css'

/** 学习时间校验：仅允许数字 0-9 与冒号 : */
const TIME_VALIDATOR = (value) => /^[0-9:]*$/.test(value)

/**
 * 推荐学科（本地占位）。
 * 后期接入后端时：根据用户学习时长与内容等数据，由本地信息 + 后端预留接口
 * 动态返回学科，替换下方 DEFAULT_SUBJECT 即可。
 */
const DEFAULT_SUBJECT = '数学 Mathematics - 函数与导数 Functions and Derivatives'

export default function StudyGuide() {
  // 「学习任务设置」的值由页面管理，便于「AUTO自动填充」程序化写入
  const [taskValue, setTaskValue] = useState('')

  const handleAutoFill = () => {
    setTaskValue(DEFAULT_SUBJECT)
  }

  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          导学计划
          <span className="en">Study Guide</span>
        </h1>

        <div className="recommend" aria-hidden="true">
          <p className="recommend-line">
            我所推荐的<span className="en">Recommendation…</span>
          </p>
          <p className="recommend-line">{DEFAULT_SUBJECT}</p>
        </div>

        <button type="button" className="auto-fill" onClick={handleAutoFill}>
          AUTO自动填充
        </button>

        <StudyEditor
          cnLabel="学习任务设置"
          enLabel="Study Task Setting"
          placeholder="e.g. 复习函数章节"
          value={taskValue}
          onChange={(event) => setTaskValue(event.target.value)}
        />

        <StudyEditor
          cnLabel="学习时间设置"
          enLabel="Study Time Setting"
          placeholder="e.g. 12:30"
          validate={TIME_VALIDATOR}
        />

        <EnterButton />
      </main>
    </>
  )
}