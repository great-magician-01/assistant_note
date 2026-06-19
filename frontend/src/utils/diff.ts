/**
 * Simple line-based diff using LCS (Longest Common Subsequence).
 * Returns a sequence of lines tagged as added, removed, or unchanged.
 */

export interface DiffLine {
  type: 'added' | 'removed' | 'unchanged'
  content: string
  /** 1-based line number in the "old" text (A), undefined for added lines. */
  lineA?: number
  /** 1-based line number in the "new" text (B), undefined for removed lines. */
  lineB?: number
}

/** Compute the LCS table for two arrays. */
function lcsTable<T>(a: T[], b: T[]): number[][] {
  const m = a.length
  const n = b.length
  const dp: number[][] = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0))
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      if (a[i - 1] === b[j - 1]) {
        dp[i][j] = dp[i - 1][j - 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i - 1][j], dp[i][j - 1])
      }
    }
  }
  return dp
}

/** Backtrack the LCS table to produce diff lines. */
function backtrack<T>(a: T[], b: T[], dp: number[][]): DiffLine[] {
  const result: DiffLine[] = []
  let i = a.length
  let j = b.length

  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i - 1] === b[j - 1]) {
      result.push({ type: 'unchanged', content: String(a[i - 1]), lineA: i, lineB: j })
      i--
      j--
    } else if (j > 0 && (i === 0 || dp[i][j - 1] >= dp[i - 1][j])) {
      result.push({ type: 'added', content: String(b[j - 1]), lineB: j })
      j--
    } else {
      result.push({ type: 'removed', content: String(a[i - 1]), lineA: i })
      i--
    }
  }

  result.reverse()
  return result
}

/**
 * Compute a line-by-line diff between two plain-text strings.
 * textA = "old" version, textB = "new" version.
 */
export function computeDiff(textA: string, textB: string): DiffLine[] {
  const linesA = (textA || '').split('\n')
  const linesB = (textB || '').split('\n')
  const dp = lcsTable(linesA, linesB)
  return backtrack(linesA, linesB, dp)
}
