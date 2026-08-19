/**
 * 右侧面板 · 录入新错题：
 * - 顶部「+ 录入新错题」按钮展开折叠表单
 * - 保存后：写入 localStorage（与错题本页共享 key）→ 通知父组件自动发消息 → 底部追加"最近录入"记录
 *
 * 学科字段说明：错题本页按 `errors_{subject}` 分学科存储，
 * 因此表单必须包含学科选择（默认数学），知识点选项随学科联动。
 */

import { useState } from 'react'
import { App as AntdApp, Button, Form, Input, Select, message } from 'antd'
import { PlusOutlined } from '@ant-design/icons'
import {
  genId,
  readErrors,
  relativeTime,
  writeErrors,
  REASON_OPTIONS,
  SUBJECT_KNOWLEDGE,
  SUBJECT_LABEL,
  type ErrorItem,
  type ErrorReason,
  type Subject,
} from './types'

interface ErrorEntryPanelProps {
  /** 保存成功后回调（父组件用来触发自动发消息 + 刷新左侧错题列表） */
  onSaved: (item: ErrorItem, subject: Subject) => void
}

interface RecentEntry {
  id: string
  preview: string
  createdAt: number
}

interface FormValues {
  subject: Subject
  questionText: string
  reason: ErrorReason
  knowledgeNames: string[]
}

function ErrorEntryInner({ onSaved }: ErrorEntryPanelProps) {
  const [messageApi, contextHolder] = message.useMessage()
  const [open, setOpen] = useState(false)
  const [recent, setRecent] = useState<RecentEntry[]>([])
  const [subject, setSubject] = useState<Subject>('math')
  const [form] = Form.useForm<FormValues>()

  const handleSave = async () => {
    try {
      const values = await form.validateFields()
      const item: ErrorItem = {
        id: genId('err'),
        questionText: values.questionText.trim(),
        reason: values.reason,
        knowledgeNames: values.knowledgeNames ?? [],
        createdAt: Date.now(),
      }
      // 与错题本页共享同一 key，前插保持倒序
      writeErrors(values.subject, [item, ...readErrors(values.subject)])
      setRecent((r) =>
        [{ id: item.id, preview: item.questionText.slice(0, 20), createdAt: item.createdAt }, ...r].slice(0, 5),
      )
      form.resetFields()
      setSubject('math')
      setOpen(false)
      messageApi.success('错题已保存')
      onSaved(item, values.subject)
    } catch {
      // antd 校验失败会自动展示红字
    }
  }

  return (
    <div className="entry-panel">
      {contextHolder}

      <Button
        type="primary"
        icon={<PlusOutlined />}
        block
        className="entry-toggle"
        onClick={() => setOpen((v) => !v)}
      >
        {open ? '收起' : '录入新错题'}
      </Button>

      {open && (
        <Form
          form={form}
          layout="vertical"
          className="entry-form"
          initialValues={{ subject: 'math', reason: 'concept', knowledgeNames: [] }}
        >
          <Form.Item label="学科" name="subject" rules={[{ required: true, message: '请选择学科' }]}>
            <Select
              options={(Object.keys(SUBJECT_LABEL) as Subject[]).map((s) => ({
                value: s,
                label: SUBJECT_LABEL[s],
              }))}
              onChange={(s: Subject) => {
                setSubject(s)
                // 切学科后清空已选知识点，避免串学科
                form.setFieldValue('knowledgeNames', [])
              }}
            />
          </Form.Item>

          <Form.Item
            label="题目原文"
            name="questionText"
            rules={[{ required: true, message: '请输入题目原文' }]}
          >
            <Input.TextArea placeholder="粘贴错题原文…" autoSize={{ minRows: 3, maxRows: 6 }} />
          </Form.Item>

          <Form.Item label="错因" name="reason" rules={[{ required: true, message: '请选择错因' }]}>
            <Select options={REASON_OPTIONS} placeholder="选择错因" />
          </Form.Item>

          <Form.Item label="关联知识点" name="knowledgeNames">
            <Select
              mode="multiple"
              allowClear
              placeholder="可多选"
              options={SUBJECT_KNOWLEDGE[subject].map((k) => ({ value: k, label: k }))}
            />
          </Form.Item>

          <Button type="primary" block onClick={handleSave}>
            保存错题
          </Button>
        </Form>
      )}

      {/* 最近录入记录 */}
      {recent.length > 0 && (
        <div className="entry-recent">
          <div className="entry-recent-title">最近录入</div>
          {recent.map((r) => (
            <div key={r.id} className="entry-recent-item">
              <span className="entry-recent-text">{r.preview}…</span>
              <span className="entry-recent-time">{relativeTime(r.createdAt)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

export default function ErrorEntryPanel(props: ErrorEntryPanelProps) {
  return (
    <AntdApp>
      <ErrorEntryInner {...props} />
    </AntdApp>
  )
}
