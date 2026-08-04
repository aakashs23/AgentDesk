import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, BookOpen, Plus, Search } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router'

import { Button } from '../../components/Button'
import { Card } from '../../components/Card'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Input } from '../../components/Input'
import { ConfirmModal } from '../../components/Modal'
import { Skeleton, SkeletonRows } from '../../components/Skeleton'
import { Tabs } from '../../components/Tabs'
import { ApiError, api } from '../../lib/api'
import { useUser } from '../../lib/auth'
import { useDebounced } from '../../lib/hooks'
import { useCategories, useSurfaceBase, useTicket } from '../../lib/queries'
import { toast } from '../../lib/toast'
import type { KbArticle, KbArticleSummary } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

/** §19 step 4: "Drafts" is the review queue — what is waiting to be published. */
const KB_TABS = [
  { id: 'all', label: 'All' },
  { id: 'draft', label: 'Drafts' },
  { id: 'published', label: 'Published' },
]

/**
 * Staff-facing KB browse. Unlike the portal's accordion this is a working
 * list — status is visible, because an agent sees their own unpublished drafts
 * alongside published articles (Doc 05 §6).
 *
 * Mounted under both `/agent/kb` and `/admin/kb`: the API already returns
 * everything an Admin may see (all drafts, all authors), so Knowledge Base
 * Management is this same screen asked by a different role, not a second one.
 */
export function AgentKnowledgeBase() {
  const [query, setQuery] = useState('')
  const [params, setParams] = useSearchParams()
  const navigate = useNavigate()
  const base = useSurfaceBase()
  const term = useDebounced(query.trim(), 300)
  const tab = params.get('status') ?? 'all'

  const articles = useQuery({
    queryKey: ['kb', term, tab],
    queryFn: () =>
      api<KbArticleSummary[]>(
        `/knowledge-base/articles?limit=50${term ? `&q=${encodeURIComponent(term)}` : ''}` +
          (tab === 'all' ? '' : `&status=${tab}`),
      ),
  })

  return (
    <div className="mx-auto max-w-[960px]">
      <div className="flex flex-wrap items-center justify-between gap-16">
        <h1 className="text-h1 font-semibold">Knowledge Base</h1>
        <Button
          variant="primary"
          icon={<Plus size={16} strokeWidth={1.5} />}
          onClick={() => navigate(`${base}/kb/new`)}
        >
          New article
        </Button>
      </div>

      <div className="mt-24">
        <Tabs
          tabs={KB_TABS}
          active={tab}
          onChange={(id) => setParams(id === 'all' ? {} : { status: id })}
        />
      </div>

      <div className="relative mt-24">
        <Search
          aria-hidden
          size={16}
          strokeWidth={1.5}
          className="text-muted absolute top-1/2 left-12 -translate-y-1/2"
        />
        <input
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search articles…"
          aria-label="Search articles"
          className={cn(
            'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] w-full border pr-12 pl-32',
            'placeholder:text-muted focus:border-primary transition-colors duration-micro',
            focusRing,
          )}
        />
      </div>

      <div className="mt-24">
        {articles.isPending && <SkeletonRows rows={5} />}

        {articles.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Couldn't load articles"
            onRetry={() => void articles.refetch()}
          />
        )}

        {articles.isSuccess && articles.data.length === 0 && (
          <EmptyState
            icon={BookOpen}
            title="No articles found"
            message="Resolve a ticket and flag it as reusable to seed the first one."
          />
        )}

        <ul className="flex flex-col gap-8">
          {(articles.data ?? []).map((article) => (
            <li key={article.id}>
              <Card interactive className="p-0">
                <Link
                  to={`${base}/kb/${article.id}`}
                  className={cn('flex items-center gap-12 p-16', focusRing)}
                >
                  <div className="min-w-0 flex-1">
                    <p className="text-body text-ink truncate font-medium">{article.title}</p>
                    <p className="text-body-sm text-muted mt-4">
                      Updated{' '}
                      <time dateTime={article.updated_at}>{relativeTime(article.updated_at)}</time>
                    </p>
                  </div>
                  <span
                    className={cn(
                      'rounded-pill text-caption shrink-0 px-12 py-4 font-medium tracking-wide uppercase',
                      article.status === 'published'
                        ? 'bg-success-fill text-white'
                        : 'border-border text-muted border',
                    )}
                  >
                    {article.status}
                  </span>
                </Link>
              </Card>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/**
 * Create or edit an article. App Flow §19: an agent drafts, an Admin publishes
 * — so the publish control only exists for an Admin, and the backend refuses it
 * regardless of what the UI renders.
 */
export function KbArticleEditor() {
  const { articleId } = useParams<{ articleId: string }>()
  const [params] = useSearchParams()
  const sourceTicketId = params.get('ticket')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useUser()
  const base = useSurfaceBase()
  const categories = useCategories()

  const editing = Boolean(articleId)
  const article = useQuery({
    queryKey: ['kb-article', articleId],
    enabled: editing,
    queryFn: () => api<KbArticle>(`/knowledge-base/articles/${articleId}`),
  })
  // Seeded from the resolved ticket when arriving via "Flag as reusable".
  const sourceTicket = useTicket(sourceTicketId ?? undefined)

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [categoryId, setCategoryId] = useState('')

  useEffect(() => {
    if (article.data) {
      setTitle(article.data.title)
      setBody(article.data.body)
      setCategoryId(article.data.category_id ?? '')
    } else if (sourceTicket.data) {
      setTitle(sourceTicket.data.subject)
      setBody(sourceTicket.data.description)
      setCategoryId(sourceTicket.data.category_id ?? '')
    }
  }, [article.data, sourceTicket.data])

  const save = useMutation({
    mutationFn: (status?: 'published') => {
      const payload = {
        title: title.trim(),
        body: body.trim(),
        category_id: categoryId || null,
        ...(status ? { status } : {}),
      }
      return editing
        ? api<KbArticle>(`/knowledge-base/articles/${articleId}`, {
            method: 'PATCH',
            json: payload,
          })
        : api<KbArticle>('/knowledge-base/articles', {
            method: 'POST',
            json: { ...payload, source_ticket_id: sourceTicketId },
          })
    },
    onSuccess: async (saved) => {
      await queryClient.invalidateQueries({ queryKey: ['kb'] })
      toast(saved.status === 'published' ? 'Article published' : 'Draft saved', 'success')
      navigate(`${base}/kb/${saved.id}`)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not save', 'error'),
  })

  if (editing && article.isPending) return <Skeleton className="h-[320px]" />

  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="text-h1 font-semibold">{editing ? 'Edit article' : 'New article'}</h1>
      {sourceTicketId && !editing && (
        <p className="text-body-sm text-muted mt-8">
          Pre-filled from {sourceTicket.data?.ref ?? 'the resolved ticket'}. Rewrite it as guidance
          before saving — a raw ticket rarely reads as an article.
        </p>
      )}

      <div className="mt-24 flex flex-col gap-16">
        <Input label="Title" value={title} onChange={(e) => setTitle(e.target.value)} />

        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Category</span>
          <select
            value={categoryId}
            onChange={(e) => setCategoryId(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary h-[44px] w-full border px-12',
              focusRing,
            )}
          >
            <option value="">Uncategorised</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-8">
          <span className="text-body-sm text-muted font-medium">Body</span>
          <textarea
            rows={16}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            className={cn(
              'rounded-control bg-sunken text-ink border-transparent focus:bg-surface focus:border-primary w-full border p-12',
              'focus:border-primary transition-colors duration-micro',
              focusRing,
            )}
          />
        </label>
      </div>

      <div className="mt-24 flex flex-wrap justify-end gap-8">
        <Button onClick={() => navigate(`${base}/kb`)}>Cancel</Button>
        <Button
          variant="primary"
          disabled={!title.trim() || !body.trim() || save.isPending}
          onClick={() => save.mutate(undefined)}
        >
          Save draft
        </Button>
        {user?.role === 'admin' && (
          <Button
            variant="primary"
            disabled={!title.trim() || !body.trim() || save.isPending}
            onClick={() => save.mutate('published')}
          >
            Publish
          </Button>
        )}
      </div>
    </div>
  )
}

/** Read view with an Edit affordance — the portal's version is read-only. */
export function AgentKbArticle() {
  const { articleId } = useParams<{ articleId: string }>()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const user = useUser()
  const base = useSurfaceBase()
  const [confirming, setConfirming] = useState(false)
  const article = useQuery({
    queryKey: ['kb-article', articleId],
    enabled: Boolean(articleId),
    queryFn: () => api<KbArticle>(`/knowledge-base/articles/${articleId}`),
  })

  /** §19 step 5: approving a draft is the whole review action, so it lives on
   *  the screen the Admin lands on from the Drafts queue — not behind Edit. */
  const publish = useMutation({
    mutationFn: () =>
      api<KbArticle>(`/knowledge-base/articles/${articleId}`, {
        method: 'PATCH',
        json: { status: 'published' },
      }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['kb'] })
      await queryClient.invalidateQueries({ queryKey: ['kb-article', articleId] })
      toast('Article published — it can be suggested on new tickets now', 'success')
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not publish', 'error'),
  })

  const remove = useMutation({
    mutationFn: () => api<void>(`/knowledge-base/articles/${articleId}`, { method: 'DELETE' }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ['kb'] })
      toast('Article deleted', 'success')
      navigate(`${base}/kb`)
    },
    onError: (e) => toast(e instanceof ApiError ? e.message : 'Could not delete', 'error'),
  })

  if (article.isPending) return <Skeleton className="h-[320px]" />
  if (article.isError) {
    return (
      <ErrorState
        icon={AlertCircle}
        title="Couldn't load this article"
        onRetry={() => void article.refetch()}
      />
    )
  }

  return (
    <div className="mx-auto max-w-[760px]">
      <div className="flex flex-wrap items-start justify-between gap-16">
        <div>
          <h1 className="text-h1 font-semibold">{article.data.title}</h1>
          <p className="text-body-sm text-muted mt-8">
            {article.data.status} · updated{' '}
            <time dateTime={article.data.updated_at}>{relativeTime(article.data.updated_at)}</time>
          </p>
        </div>
        <div className="flex gap-8">
          {user?.role === 'admin' && article.data.status === 'draft' && (
            <Button variant="primary" disabled={publish.isPending} onClick={() => publish.mutate()}>
              Publish
            </Button>
          )}
          <Button onClick={() => navigate(`${base}/kb/${article.data.id}/edit`)}>Edit</Button>
          {/* Doc 03 §1 gives Admin full CRUD; the API refuses a delete from
              anyone else, author or not. */}
          {user?.role === 'admin' && (
            <Button variant="ghost" onClick={() => setConfirming(true)}>
              Delete
            </Button>
          )}
        </div>
      </div>
      <div className="text-body mt-24 whitespace-pre-wrap">{article.data.body}</div>

      <ConfirmModal
        open={confirming}
        onClose={() => setConfirming(false)}
        onConfirm={() => remove.mutate()}
        title="Delete this article?"
        message="It stops being suggested on new tickets immediately. The audit entry survives it."
        confirmLabel="Delete"
        destructive
      />
    </div>
  )
}
