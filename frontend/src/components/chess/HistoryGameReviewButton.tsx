import { useMutation } from "@tanstack/react-query"

import { Button } from "@/components/ui/button"
import { getGameReview } from "@/features/chess/api"
import useCustomToast from "@/hooks/useCustomToast"

type HistoryGameReviewButtonProps = {
  gameId: string
}

export function HistoryGameReviewButton({ gameId }: HistoryGameReviewButtonProps) {
  const { showErrorToast, showSuccessToast } = useCustomToast()

  const reviewMutation = useMutation({
    mutationFn: () => getGameReview(gameId, true),
    onSuccess: () => {
      showSuccessToast(`Game review generated for ${gameId}.`)
    },
    onError: (error) => {
      showErrorToast((error as Error).message)
    },
  })

  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      disabled={reviewMutation.isPending}
      onClick={() => reviewMutation.mutate()}
    >
      {reviewMutation.isPending ? "Running..." : "Run review"}
    </Button>
  )
}
