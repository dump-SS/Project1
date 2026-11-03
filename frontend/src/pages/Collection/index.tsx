/**
 * 收藏页（E 板块）· /collection
 *
 * 对应 M4→M5 验收门判据「收藏快照可读」（refactor-development-plan.md 第 208 行）。
 * 设计口径 docs/product-redesign-target.md §4.8：
 * - 第 798 行：知识页 = 课内、有结构、可评测；**收藏 = 一切、无结构、不可评测**
 * - 第 803 行：存快照不存引用，所以这里渲染的是 snapshot.content 本体
 * - 第 815-816 行：自定义分组是标签字段、内置维度是筛选维度；chat 收藏**只需自定义分组 + 时间排序**
 * - 第 817 行：卡片 + 来源引用，**不做文本直列**
 * - 第 821 行：内容不可编辑——本页没有任何编辑正文的入口，只有标题与分组
 *
 * 「虚化 / 高亮」标记（#41，第 823-827 行）在展开态里做，见 CollectionSnapshotView。
 */
import { useCallback, useEffect, useMemo, useState } from 'react'
import styles from './index.module.css'
import SnapshotView from './SnapshotView'
import { ApiError } from '@/services/http'
import {
  COLLECTION_SOURCE_TYPE_LABEL,
  createCollection,
  deleteCollection,
  deleteCollectionItem,
  fetchCollectionItem,
  fetchCollectionItems,
  fetchCollections,
  renameCollection,
  updateCollectionItem,
  type CollectionGroup,
  type CollectionItem,
  type CollectionItemUpdate,
} from '@/services/collection'

/** 分组筛选的两个伪值：真分组 ID 不会是这两个字符串 */
const GROUP_ALL = '__all__'
const GROUP_NONE = '__none__'

function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    // 409 = 分组重名，400 = 撞了内置分组名（学科/时间/掌握度是筛选维度、不入表）
    if (err.status === 409) return `分组名已存在：${err.message}`
    if (err.status === 400) return `分组名不可用：${err.message}`
    return err.message
  }
  return err instanceof Error ? err.message : '加载失败'
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

export default function CollectionPage() {
  const [groups, setGroups] = useState<CollectionGroup[]>([])
  const [items, setItems] = useState<CollectionItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [activeGroup, setActiveGroup] = useState(GROUP_ALL)
  const [newGroupName, setNewGroupName] = useState('')
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  /**
   * @param silent 写操作后的重读传 true。
   * 非静默会把列表整块换成「加载中…」，卡片因此卸载、展开态与单条 detail 全部丢失
   * （真跑实测：标完虚化后卡片自己收起来了）。首屏才需要那个占位。
   */
  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true)
    setError(null)
    try {
      const [groupRes, itemRes] = await Promise.all([fetchCollections(), fetchCollectionItems()])
      setGroups(groupRes.items ?? [])
      setItems(itemRes.items ?? [])
    } catch (err) {
      setError(describeError(err))
    } finally {
      if (!silent) setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  const visibleItems = useMemo(() => {
    if (activeGroup === GROUP_ALL) return items
    if (activeGroup === GROUP_NONE) return items.filter((it) => !it.collectionId)
    return items.filter((it) => it.collectionId === activeGroup)
  }, [items, activeGroup])

  const countOf = useCallback(
    (key: string) => {
      if (key === GROUP_ALL) return items.length
      if (key === GROUP_NONE) return items.filter((it) => !it.collectionId).length
      return items.filter((it) => it.collectionId === key).length
    },
    [items],
  )

  const groupName = useCallback(
    (id: string | null | undefined) => groups.find((g) => g.collectionId === id)?.name ?? null,
    [groups],
  )

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await action()
    } catch (err) {
      setError(describeError(err))
    } finally {
      setBusy(false)
    }
  }

  const onCreateGroup = () => {
    const name = newGroupName.trim()
    if (!name) return
    void run(async () => {
      await createCollection(name)
      setNewGroupName('')
      await load(true)
    })
  }

  const onRenameGroup = (collectionId: string) => {
    const name = renameValue.trim()
    if (!name) return
    void run(async () => {
      await renameCollection(collectionId, name)
      setRenamingId(null)
      await load(true)
    })
  }

  const onDeleteGroup = (group: CollectionGroup) => {
    if (!window.confirm(`删除分组「${group.name}」？组内收藏只会移出分组，不会被删除。`)) return
    void run(async () => {
      await deleteCollection(group.collectionId)
      if (activeGroup === group.collectionId) setActiveGroup(GROUP_ALL)
      await load(true)
    })
  }

  const onMoveItem = (item: CollectionItem, collectionId: string | null) => {
    void run(async () => {
      await updateCollectionItem(item.itemId, { collectionId })
      await load(true)
    })
  }

  const onDeleteItem = (item: CollectionItem) => {
    const label = item.title || item.snapshot.content.slice(0, 20)
    if (!window.confirm(`删除这条收藏？\n${label}`)) return
    void run(async () => {
      await deleteCollectionItem(item.itemId)
      await load(true)
    })
  }

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>收藏</h1>
        <p className={styles.subtitle}>
          任何模型输出都能留一份快照。收藏不进知识点库、不参与评测——存的是内容本体，原文过期也照样能读。
        </p>
      </header>

      <div className={styles.groupBar}>
        <button
          type="button"
          className={`${styles.chip} ${activeGroup === GROUP_ALL ? styles.chipActive : ''}`}
          onClick={() => setActiveGroup(GROUP_ALL)}
        >
          全部<span className={styles.chipCount}>{countOf(GROUP_ALL)}</span>
        </button>
        <button
          type="button"
          className={`${styles.chip} ${activeGroup === GROUP_NONE ? styles.chipActive : ''}`}
          onClick={() => setActiveGroup(GROUP_NONE)}
        >
          未分组<span className={styles.chipCount}>{countOf(GROUP_NONE)}</span>
        </button>
        {groups.map((g) => (
          <button
            key={g.collectionId}
            type="button"
            className={`${styles.chip} ${activeGroup === g.collectionId ? styles.chipActive : ''}`}
            onClick={() => setActiveGroup(g.collectionId)}
          >
            {g.name}
            <span className={styles.chipCount}>{countOf(g.collectionId)}</span>
          </button>
        ))}
      </div>

      <div className={styles.groupTools}>
        <input
          className={styles.input}
          value={newGroupName}
          placeholder="新建分组名（如「计划」「闲聊」）"
          maxLength={64}
          onChange={(e) => setNewGroupName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') onCreateGroup()
          }}
        />
        <button
          type="button"
          className={`${styles.button} ${styles.buttonPrimary}`}
          disabled={busy || !newGroupName.trim()}
          onClick={onCreateGroup}
        >
          新建分组
        </button>
        {groups.map((g) =>
          renamingId === g.collectionId ? (
            <span key={g.collectionId} className={styles.groupTools}>
              <input
                className={styles.input}
                value={renameValue}
                maxLength={64}
                autoFocus
                onChange={(e) => setRenameValue(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') onRenameGroup(g.collectionId)
                  if (e.key === 'Escape') setRenamingId(null)
                }}
              />
              <button
                type="button"
                className={styles.button}
                disabled={busy || !renameValue.trim()}
                onClick={() => onRenameGroup(g.collectionId)}
              >
                保存
              </button>
              <button type="button" className={styles.button} onClick={() => setRenamingId(null)}>
                取消
              </button>
            </span>
          ) : (
            <span key={g.collectionId} className={styles.groupTools}>
              <button
                type="button"
                className={styles.button}
                disabled={busy}
                onClick={() => {
                  setRenamingId(g.collectionId)
                  setRenameValue(g.name)
                }}
              >
                改名「{g.name}」
              </button>
              <button
                type="button"
                className={`${styles.button} ${styles.buttonDanger}`}
                disabled={busy}
                onClick={() => onDeleteGroup(g)}
              >
                删除
              </button>
            </span>
          ),
        )}
      </div>

      {error && <div className={`${styles.notice} ${styles.noticeError}`}>{error}</div>}

      {loading ? (
        <div className={styles.notice}>加载中…</div>
      ) : visibleItems.length === 0 ? (
        <div className={styles.empty}>
          这里还没有收藏。在 AI 辅导里划选一段模型输出，工具条上点「收藏」就会存一份快照到这里。
        </div>
      ) : (
        <div className={styles.list}>
          {visibleItems.map((item) => (
            <CollectionCard
              key={item.itemId}
              item={item}
              groups={groups}
              groupName={groupName(item.collectionId)}
              busy={busy}
              onMove={onMoveItem}
              onDelete={onDeleteItem}
              run={run}
              reload={() => load(true)}
            />
          ))}
        </div>
      )}
    </div>
  )
}

interface CardProps {
  item: CollectionItem
  groups: CollectionGroup[]
  groupName: string | null
  busy: boolean
  onMove: (item: CollectionItem, collectionId: string | null) => void
  onDelete: (item: CollectionItem) => void
  /** 页面级的「跑一个写操作」包装：统一管 busy 与错误提示 */
  run: (action: () => Promise<unknown>) => Promise<void>
  /** 写成功后重读列表 */
  reload: () => Promise<void>
}

function CollectionCard({
  item,
  groups,
  groupName,
  busy,
  onMove,
  onDelete,
  run,
  reload,
}: CardProps) {
  const [expanded, setExpanded] = useState(false)
  const [detail, setDetail] = useState<CollectionItem | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)

  const toggle = () => {
    const next = !expanded
    setExpanded(next)
    if (next && detail === null) {
      // 展开时单独取一次单条：列表接口是概览，虚化/高亮标记以单条为准
      fetchCollectionItem(item.itemId)
        .then(setDetail)
        .catch((err) => setDetailError(describeError(err)))
    }
  }

  const shown = detail ?? item

  /** 标记变更（#41）：契约定 highlights / blurStates 全量覆盖，提交后以响应为准刷新本卡 */
  const persistMarks = (patch: CollectionItemUpdate) => {
    void run(async () => {
      const updated = await updateCollectionItem(shown.itemId, patch)
      setDetail(updated)
      setDetailError(null)
      await reload()
    })
  }

  return (
    <article className={styles.card}>
      <div className={styles.cardTop}>
        <h2 className={styles.cardTitle}>{item.title || '未命名收藏'}</h2>
      </div>

      <div className={styles.cardMeta}>
        {shown.sourceRef?.type && (
          <span className={styles.tag}>
            {COLLECTION_SOURCE_TYPE_LABEL[shown.sourceRef.type] ?? shown.sourceRef.type}
          </span>
        )}
        {shown.sourceRef?.label && <span className={styles.tag}>{shown.sourceRef.label}</span>}
        {groupName && <span className={styles.tag}>{groupName}</span>}
        <span>{formatTime(item.createdAt)}</span>
        {shown.blurStates?.length ? <span>{shown.blurStates.length} 处虚化</span> : null}
      </div>

      {!expanded && <p className={styles.preview}>{shown.snapshot.content}</p>}

      {expanded && (
        <div>
          {detailError && (
            <div className={`${styles.notice} ${styles.noticeError}`}>{detailError}</div>
          )}
          <SnapshotView item={shown} busy={busy} onPersist={persistMarks} />
        </div>
      )}

      <div className={styles.cardActions}>
        <button type="button" className={styles.button} onClick={toggle}>
          {expanded ? '收起' : '展开全文'}
        </button>
        <select
          className={styles.input}
          value={item.collectionId ?? GROUP_NONE}
          disabled={busy}
          aria-label="移动到分组"
          onChange={(e) => {
            const v = e.target.value
            onMove(item, v === GROUP_NONE ? null : v)
          }}
        >
          <option value={GROUP_NONE}>未分组</option>
          {groups.map((g) => (
            <option key={g.collectionId} value={g.collectionId}>
              {g.name}
            </option>
          ))}
        </select>
        <button
          type="button"
          className={`${styles.button} ${styles.buttonDanger}`}
          disabled={busy}
          onClick={() => onDelete(item)}
        >
          删除
        </button>
      </div>
    </article>
  )
}
