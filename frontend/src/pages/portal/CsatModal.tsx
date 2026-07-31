import { useQueryClient } from '@tanstack/react-query'
import { Star } from 'lucide-react'
import { useState } from 'react'

import { Button } from '../../components/Button'
import { Modal } from '../../components/Modal'
import { ApiError, api } from '../../lib/api'
import { toast } from '../../lib/toast'
import { cn, focusRing } from '../../lib/ui'

const RATINGS = [1, 2, 3, 4, 5]

/**
 * The CSAT survey (App Flow Doc 03 §5 step 6, §7). Shown over Ticket Detail on
 * the requester's next visit once the ticket is resolved; dismissible, because
 * Doc 03 lists "Submit / Dismiss" as its actions.
 */
export function CsatModal({
  open,
  onClose,
  ticketId,
}: {
  open: boolean
  onClose: () => void
  ticketId: string
}) {
  const queryClient = useQueryClient()
  const [rating, setRating] = useState<number | null>(null)
  const [comment, setComment] = useState('')
  const [saving, setSaving] = useState(false)

  async function submit() {
    if (rating === null) return
    setSaving(true)
    try {
      await api('/csat', {
        method: 'POST',
        json: { ticket_id: ticketId, rating, comment: comment.trim() || null },
      })
      await queryClient.invalidateQueries({ queryKey: ['csat', ticketId] })
      toast('Thanks for the feedback', 'success')
      onClose()
    } catch (err) {
      toast(err instanceof ApiError ? err.message : 'Could not submit your rating', 'error')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="How did we do?"
      size="confirm"
      footer={
        <>
          <Button onClick={onClose}>Not now</Button>
          <Button variant="primary" disabled={rating === null || saving} onClick={submit}>
            Submit
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-16">
        <p className="text-body text-muted">
          Your rating helps us understand how well this request was handled.
        </p>

        <div role="radiogroup" aria-label="Satisfaction rating" className="flex gap-8">
          {RATINGS.map((value) => {
            const selected = rating !== null && value <= rating
            return (
              <button
                key={value}
                type="button"
                role="radio"
                aria-checked={rating === value}
                aria-label={`${value} out of 5`}
                onClick={() => setRating(value)}
                className={cn(
                  'rounded-control flex size-[44px] cursor-pointer items-center justify-center',
                  'transition-colors duration-micro',
                  selected ? 'text-high' : 'text-muted hover:text-ink',
                  focusRing,
                )}
              >
                <Star size={24} strokeWidth={1.5} fill={selected ? 'currentColor' : 'none'} />
              </button>
            )
          })}
        </div>

        <div className="flex flex-col gap-8">
          <label htmlFor="csat-comment" className="text-body-sm text-muted font-medium">
            Anything to add? (optional)
          </label>
          <textarea
            id="csat-comment"
            rows={3}
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            className={cn(
              'rounded-control border-border bg-canvas text-ink w-full border p-12',
              'placeholder:text-muted focus:border-brand-start transition-colors duration-micro',
              focusRing,
            )}
          />
        </div>
      </div>
    </Modal>
  )
}
