import StudyEditor from '../components/StudyEditor.jsx'
import EnterButton from '../components/EnterButton.jsx'

/** 学习时间校验：仅允许数字 0-9 与冒号 : */
const TIME_VALIDATOR = (value) => /^[0-9:]*$/.test(value)

export default function StudyPlanEditor() {
  return (
    <>
      <div className="page-background" aria-hidden="true" />
      <main className="app">
        <h1 className="page-title">
          学习计划编辑
          <br />
          <span className="en">Study Plan Editor</span>
        </h1>

        <StudyEditor
          cnLabel="学习时间设置"
          enLabel="Study Time Setting"
          placeholder="e.g. 12:30"
          validate={TIME_VALIDATOR}
        />

        <StudyEditor
          cnLabel="学习任务设置"
          enLabel="Study Task Setting"
          placeholder="e.g. 复习函数章节"
        />

        <EnterButton />
      </main>
    </>
  )
}