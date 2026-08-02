import { useQuery } from '@tanstack/react-query'
import { AlertCircle, ArrowLeft, BookOpen, Search } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'

import { Accordion } from '../../components/Accordion'
import { Button } from '../../components/Button'
import { EmptyState, ErrorState } from '../../components/EmptyState'
import { Skeleton, SkeletonRows } from '../../components/Skeleton'
import { api } from '../../lib/api'
import { useDebounced } from '../../lib/hooks'
import type { KbArticle, KbArticleSummary } from '../../lib/types'
import { cn, focusRing, relativeTime } from '../../lib/ui'

export function KnowledgeBaseSearch() {
  const [query, setQuery] = useState('')
  const navigate = useNavigate()
  const term = useDebounced(query.trim(), 300)

  const articles = useQuery({
    queryKey: ['kb', term],
    queryFn: () =>
      api<KbArticleSummary[]>(
        `/knowledge-base/articles?limit=50${term ? `&q=${encodeURIComponent(term)}` : ''}`,
      ),
  })

  return (
    <div className="mx-auto max-w-[760px]">
      <h1 className="text-h1 font-semibold">Knowledge Base</h1>
      <p className="text-body text-muted mt-8">
        Search our guides — you may find an answer faster than raising a ticket.
      </p>

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
        {articles.isPending && <SkeletonRows rows={4} />}

        {articles.isError && (
          <ErrorState
            icon={AlertCircle}
            title="Search is temporarily unavailable"
            onRetry={() => void articles.refetch()}
          />
        )}

        {articles.isSuccess && articles.data.length === 0 && (
          <EmptyState
            icon={BookOpen}
            title="No articles found"
            message="Nothing matches that search. If you can't find an answer, raise a ticket and we'll help."
            action={
              <Button variant="primary" onClick={() => navigate('/portal/tickets/new')}>
                Submit a ticket
              </Button>
            }
          />
        )}

        {/* Doc 04 lists the FAQ/accordion as the reusable KB browsing pattern:
            skim the titles, expand the likely one, open it fully if it helps. */}
        {articles.isSuccess && articles.data.length > 0 && (
          <Accordion
            items={articles.data.map((article) => ({
              id: article.id,
              title: article.title,
              content: <ArticlePreview article={article} />,
            }))}
          />
        )}
      </div>
    </div>
  )
}

/** Lazily loads the body only when its accordion item is opened. */
function ArticlePreview({ article }: { article: KbArticleSummary }) {
  const detail = useQuery({
    queryKey: ['kb-article', article.id],
    queryFn: () => api<KbArticle>(`/knowledge-base/articles/${article.id}`),
  })

  if (detail.isPending) return <Skeleton className="h-[48px]" />
  if (detail.isError)
    return <p className="text-body-sm text-critical">Couldn't load this article.</p>

  return (
    <div className="flex flex-col gap-12">
      <p className="line-clamp-4 whitespace-pre-wrap">{detail.data.body}</p>
      <Link
        to={`/portal/kb/${article.id}`}
        className={cn(
          'text-body-sm text-primary font-medium underline underline-offset-4',
          focusRing,
        )}
      >
        Read the full article
      </Link>
    </div>
  )
}

export function KbArticleDetail() {
  const { articleId } = useParams<{ articleId: string }>()
  const article = useQuery({
    queryKey: ['kb-article', articleId],
    enabled: Boolean(articleId),
    queryFn: () => api<KbArticle>(`/knowledge-base/articles/${articleId}`),
  })

  return (
    <div className="mx-auto max-w-[760px]">
      <Link
        to="/portal/kb"
        className={cn(
          'text-body-sm text-muted hover:text-ink inline-flex items-center gap-8',
          focusRing,
        )}
      >
        <ArrowLeft aria-hidden size={16} strokeWidth={1.5} />
        Knowledge Base
      </Link>

      {article.isPending && (
        <div className="mt-24 flex flex-col gap-16">
          <Skeleton className="h-[32px] w-2/3" />
          <Skeleton className="h-[160px]" />
        </div>
      )}

      {article.isError && (
        <ErrorState
          icon={AlertCircle}
          title="Couldn't load this article"
          onRetry={() => void article.refetch()}
        />
      )}

      {article.isSuccess && (
        <article className="mt-16">
          <h1 className="text-h1 font-semibold">{article.data.title}</h1>
          <p className="text-body-sm text-muted mt-8">
            Updated{' '}
            <time dateTime={article.data.updated_at}>{relativeTime(article.data.updated_at)}</time>
          </p>
          <div className="text-body mt-24 whitespace-pre-wrap">{article.data.body}</div>
        </article>
      )}
    </div>
  )
}
